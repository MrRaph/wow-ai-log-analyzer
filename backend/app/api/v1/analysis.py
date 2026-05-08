"""Endpoints for AI analyses."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from app.core.errors import ForbiddenError, NotFoundError
from app.deps import CurrentUser, LocaleDep, SessionDep
from app.models import (
    Analysis,
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
    PaginatedAnalyses,
)
from app.services.ai import analyzer
from app.services.wow_data_service import resolve_encounter_names_with_fallback

router = APIRouter()


@router.post("", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    payload: AnalysisIn,
    session: SessionDep,
    user: CurrentUser,
    locale: LocaleDep,
) -> AnalysisOut:
    analysis = await analyzer.request_analysis(
        session,
        report_id=payload.report_id,
        fight_id=payload.fight_id,
        player_id=payload.player_id,
        requested_by_id=user.id,
        locale=user.locale or locale,
    )
    await session.commit()
    # ``updated_at`` has ``onupdate=func.now()``, which SQLAlchemy treats as
    # server-computed → after the commit the column is "expired" and Pydantic
    # would trigger a sync IO when reading it. Refresh in-place so the model
    # walk is purely in-memory.
    await session.refresh(analysis)
    return AnalysisOut.model_validate(analysis)


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
    if user_locale not in {"en", "de"}:
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
async def get_analysis(analysis_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> AnalysisOut:
    row = (
        await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not row:
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
