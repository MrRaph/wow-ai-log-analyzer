"""Endpoints for AI analyses."""
from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from app.core.errors import ForbiddenError, NotFoundError
from app.deps import ArqDep, CurrentUser, LocaleDep, SessionDep
from app.models import (
    Analysis,
    AnalysisStatus,
    Report,
    ReportFight,
    ReportPlayer,
    UserRole,
    WowLocalization,
)
from app.schemas.analysis import (
    AnalysisIn,
    AnalysisListItem,
    AnalysisOut,
    AnalysisPublicOut,
    PaginatedAnalyses,
)
from app.services.ai import analyzer
from app.services.wow_data_service import resolve_encounter_names_with_fallback

router = APIRouter()


@router.post("", response_model=AnalysisOut, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    payload: AnalysisIn,
    session: SessionDep,
    user: CurrentUser,
    locale: LocaleDep,
    arq: ArqDep,
) -> AnalysisOut:
    """Create a pending Analysis row and enqueue the worker to run it.

    Returns 202 with ``status="pending"``. The frontend polls
    ``GET /analyses/{id}`` until ``status`` is ``succeeded`` or ``failed``.
    """
    # AuthZ: requester must own the target report (admins can analyse any).
    # Without this an attacker who guesses report IDs could exfiltrate the
    # AI's findings about other users' raids since requested_by_id is set
    # to the caller — they'd then be allowed to read the result.
    target_report = (
        await session.execute(
            select(Report.owner_user_id).where(Report.id == payload.report_id)
        )
    ).scalar_one_or_none()
    if target_report is None:
        raise NotFoundError("Report not found.")
    if target_report != user.id and user.role != UserRole.admin:
        raise NotFoundError("Report not found.")

    if payload.use_own_ai:
        # User wants the BYOK path — they must have a config saved.
        from app.services.user_ai_service import get_config as _get_user_ai_cfg

        cfg = await _get_user_ai_cfg(session, user.id)
        if cfg is None:
            raise ForbiddenError(
                "You do not have a personal AI configuration. Add one in "
                "your profile, or run the analysis with the app-wide AI."
            )
    else:
        # Validate the app-wide AI is actually available.
        from app.models import AppSetting

        setting = (
            await session.execute(
                select(AppSetting).where(AppSetting.key == "ai_provider")
            )
        ).scalar_one_or_none()
        active = (setting.value or {}).get("value") if setting and setting.value else None
        if active is None:
            from app.config import settings as _s

            active = _s.ai_provider
        if active == "disabled":
            raise ForbiddenError(
                "The app-wide AI analysis has been disabled by the admin. "
                "Use your own AI configuration from the profile page."
            )

    placeholder = Analysis(
        requested_by_id=user.id,
        report_id=payload.report_id,
        fight_id=payload.fight_id,
        player_id=payload.player_id,
        locale=user.locale or locale,
        status=AnalysisStatus.pending,
        provider="",
        model="",
        uses_byok=payload.use_own_ai,
    )
    session.add(placeholder)
    await session.commit()
    await session.refresh(placeholder)

    await arq.enqueue_job("run_analysis_task", str(placeholder.id))
    return AnalysisOut.model_validate(placeholder)


@router.get("", response_model=PaginatedAnalyses)
async def list_my_analyses(
    session: SessionDep,
    user: CurrentUser,
    locale: LocaleDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    q: str | None = Query(default=None, description="Substring search on character + boss name."),
) -> PaginatedAnalyses:
    """Paginated list of the calling user's own analyses with optional search.

    ``q`` matches against the player name and the fight's name (WCL English
    name). For boss names typed in the user's locale we additionally translate
    via the ``wow_localizations`` cache so e.g. searching "Imperator" in DE
    finds the EN-stored fight name.
    """
    user_locale = (user.locale or locale or "en").lower()
    if user_locale not in {"en", "de", "fr"}:
        user_locale = "en"

    base = (
        select(Analysis)
        .join(ReportPlayer, ReportPlayer.id == Analysis.player_id)
        .join(ReportFight, ReportFight.id == Analysis.fight_id)
        .where(Analysis.requested_by_id == user.id)
    )

    q_str = (q or "").strip()
    if q_str:
        like = f"%{q_str}%"
        # English fight names that match — used directly.
        en_matches = list(
            (
                await session.execute(
                    select(WowLocalization.name).where(
                        WowLocalization.kind == "encounter",
                        WowLocalization.locale == "en",
                        WowLocalization.name.ilike(like),
                    )
                )
            ).scalars().all()
        )
        # If the user typed in their locale (e.g. "Imperator" → de), find the
        # matching DBC IDs there and pull the EN names that share those IDs.
        if user_locale != "en":
            de_dbc_ids = list(
                (
                    await session.execute(
                        select(WowLocalization.game_id).where(
                            WowLocalization.kind == "encounter",
                            WowLocalization.locale == user_locale,
                            WowLocalization.name.ilike(like),
                        )
                    )
                ).scalars().all()
            )
            if de_dbc_ids:
                cross = list(
                    (
                        await session.execute(
                            select(WowLocalization.name).where(
                                WowLocalization.kind == "encounter",
                                WowLocalization.locale == "en",
                                WowLocalization.game_id.in_(de_dbc_ids),
                            )
                        )
                    ).scalars().all()
                )
                en_matches.extend(cross)

        clauses = [ReportPlayer.name.ilike(like), ReportFight.name.ilike(like)]
        if en_matches:
            clauses.append(ReportFight.name.in_(set(en_matches)))
        base = base.where(or_(*clauses))

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            base.order_by(Analysis.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    if not rows:
        return PaginatedAnalyses(items=[], total=int(total), page=page, page_size=page_size)

    fight_ids = {r.fight_id for r in rows}
    player_ids = {r.player_id for r in rows}
    report_ids = {r.report_id for r in rows}

    fights = {
        f.id: f
        for f in (
            await session.execute(select(ReportFight).where(ReportFight.id.in_(fight_ids)))
        ).scalars()
    }
    players = {
        p.id: p
        for p in (
            await session.execute(select(ReportPlayer).where(ReportPlayer.id.in_(player_ids)))
        ).scalars()
    }
    reports = {
        r.id: r
        for r in (
            await session.execute(select(Report).where(Report.id.in_(report_ids)))
        ).scalars()
    }

    enc_pairs: list[tuple[int, str]] = []
    for f in fights.values():
        if f.encounter_id:
            enc_pairs.append((int(f.encounter_id), f.name or ""))
    enc_name_map = await resolve_encounter_names_with_fallback(
        session, locale=user_locale, encounters=enc_pairs
    )

    items: list[AnalysisListItem] = []
    for a in rows:
        f = fights.get(a.fight_id)
        p = players.get(a.player_id)
        rep = reports.get(a.report_id)
        structured: Any = a.structured or {}
        items.append(
            AnalysisListItem(
                id=a.id,
                status=a.status,
                locale=a.locale,
                provider=a.provider,
                model=a.model,
                created_at=a.created_at,
                headline=str(structured.get("headline", ""))
                if isinstance(structured, dict)
                else "",
                overall_score=(
                    int(structured["overall_score"])
                    if isinstance(structured, dict) and structured.get("overall_score") is not None
                    else None
                ),
                role_focus=(
                    str(structured.get("role_focus"))
                    if isinstance(structured, dict) and structured.get("role_focus")
                    else None
                ),
                report_id=a.report_id,
                report_code=rep.wcl_code if rep else "",
                wcl_flavor=rep.wcl_flavor if rep else "retail",
                fight_id=a.fight_id,
                fight_name=f.name if f else "",
                fight_name_localized=(
                    enc_name_map.get(int(f.encounter_id)) if f and f.encounter_id else None
                ),
                encounter_id=f.encounter_id if f else None,
                player_id=a.player_id,
                player_name=p.name if p else "",
                player_class=p.class_slug if p else "",
                player_spec=p.spec_slug if p else "",
            )
        )
    return PaginatedAnalyses(
        items=items, total=int(total), page=page, page_size=page_size
    )


@router.get("/{analysis_id}", response_model=AnalysisOut)
async def get_analysis(
    analysis_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> AnalysisOut:
    row = (
        await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Analysis not found.")
    # Owner-or-admin gate. 404 (not 403) so we don't leak existence of an
    # analysis the caller is not authorised to see.
    if row.requested_by_id != user.id and user.role != UserRole.admin:
        raise NotFoundError("Analysis not found.")
    return AnalysisOut.model_validate(row)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> None:
    row = (
        await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Analysis not found.")
    if row.requested_by_id != user.id and user.role != UserRole.admin:
        raise ForbiddenError("You can only delete your own analyses.")
    await session.delete(row)
    await session.commit()


# --- Public share (per-analysis opt-in) --------------------------------------


def _make_share_token() -> str:
    """Generate a cryptographically random URL-safe token.

    ``token_urlsafe(32)`` yields a 43-character base64url string with 256
    bits of entropy — guessing one is statistically impossible even at
    internet-scale brute force, and the column is unique-indexed so a
    fluke collision would be rejected by the DB rather than leaking
    another user's analysis.
    """
    return secrets.token_urlsafe(32)


@router.post("/{analysis_id}/share", response_model=AnalysisOut)
async def enable_analysis_share(
    analysis_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> AnalysisOut:
    """Mint a share token for one analysis, or return the existing one.

    Idempotent: re-calling on an already-shared analysis returns the same
    token. The owner can rotate by calling ``DELETE`` then ``POST`` again.
    """
    row = (
        await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Analysis not found.")
    if row.requested_by_id != user.id and user.role != UserRole.admin:
        raise ForbiddenError("You can only share your own analyses.")
    if not row.share_token:
        row.share_token = _make_share_token()
        await session.commit()
        await session.refresh(row)
    return AnalysisOut.model_validate(row)


@router.delete("/{analysis_id}/share", response_model=AnalysisOut)
async def disable_analysis_share(
    analysis_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> AnalysisOut:
    """Revoke the share token. The link becomes 404 for anonymous viewers.

    Returning the updated analysis row keeps the frontend cache in sync
    with one round-trip — no need for a separate refetch to flip the
    "Share is on" badge off.
    """
    row = (
        await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Analysis not found.")
    if row.requested_by_id != user.id and user.role != UserRole.admin:
        raise ForbiddenError("You can only share your own analyses.")
    if row.share_token is not None:
        row.share_token = None
        await session.commit()
        await session.refresh(row)
    return AnalysisOut.model_validate(row)


async def fetch_shared_analysis(
    share_token: str, session: SessionDep, locale: LocaleDep
) -> AnalysisPublicOut:
    """Anonymous read of an analysis by its share token. No auth required.

    Returns 404 (not 401/403) for any unknown token so the endpoint can't
    be used as an oracle: an attacker probing token strings sees identical
    responses for "doesn't exist" vs "exists but private" — but the
    private case never reaches us because the token IS the private flag.

    We strip every field that could pivot to other resources or leak
    owner / billing metadata. See ``AnalysisPublicOut`` for the exact
    shape.
    """
    # Single-roundtrip pull with the joined rows we need to render
    # encounter / player display strings without auth.
    row = (
        await session.execute(
            select(Analysis).where(Analysis.share_token == share_token)
        )
    ).scalar_one_or_none()
    if not row or not row.share_token:
        raise NotFoundError("Shared analysis not found.")
    fight = (
        await session.execute(select(ReportFight).where(ReportFight.id == row.fight_id))
    ).scalar_one_or_none()
    player = (
        await session.execute(select(ReportPlayer).where(ReportPlayer.id == row.player_id))
    ).scalar_one_or_none()
    report = (
        await session.execute(select(Report).where(Report.id == row.report_id))
    ).scalar_one_or_none()

    # Localised encounter name in the viewer's locale (not the owner's,
    # so a German viewer sees German boss names on an English analysis).
    fight_name_localized: str | None = None
    if fight and fight.encounter_id:
        names = await resolve_encounter_names_with_fallback(
            session,
            locale=(locale or row.locale or "en"),
            encounters=[(int(fight.encounter_id), fight.name or "")],
        )
        fight_name_localized = names.get(int(fight.encounter_id))

    return AnalysisPublicOut(
        id=row.id,
        status=row.status,
        locale=row.locale,
        provider=row.provider,
        model=row.model,
        summary=row.summary,
        structured=row.structured or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
        report_code=report.wcl_code if report else "",
        fight_name=fight.name if fight else "",
        fight_name_localized=fight_name_localized,
        encounter_id=fight.encounter_id if fight else None,
        is_kill=bool(fight.is_kill) if fight else False,
        duration_ms=int(fight.duration_ms) if fight else 0,
        boss_percentage=fight.boss_percentage if fight else None,
        game_version=report.game_version if report else "retail",
        player_name=player.name if player else "",
        player_server=player.server if player else "",
        player_class=player.class_slug if player else "",
        player_spec=player.spec_slug if player else "",
    )
