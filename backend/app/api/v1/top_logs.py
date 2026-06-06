"""Endpoints for browsing top logs and (admin) refreshing them."""
from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.config import settings
from app.core.errors import NotFoundError, ValidationAppError
from app.deps import AdminUser, CurrentUser, LocaleDep, SessionDep
from app.models import GameSpec
from app.schemas.analysis import TopLogOut
from app.services import top_logs_service
from app.services.wow_data_service import resolve_encounter_names_with_fallback

router = APIRouter()


@router.get("", response_model=list[TopLogOut])
async def list_top_logs(
    session: SessionDep,
    user: CurrentUser,
    locale: LocaleDep,
    spec_slug: str = Query(..., description="GameSpec slug, e.g. 'priest_holy'"),
    encounter_id: int | None = Query(default=None),
    metric: str | None = Query(default=None, pattern=r"^(dps|hps)$"),
    wcl_flavor: str = Query(default="retail", pattern=r"^(retail|fresh|classic)$"),
) -> list[TopLogOut]:
    if wcl_flavor == "fresh" and not settings.top_logs_fresh_enabled:
        return []
    rows = await top_logs_service.list_top_logs(
        session,
        spec_slug=spec_slug,
        encounter_id=encounter_id,
        metric=metric,
        wcl_flavor=wcl_flavor,
    )
    pairs = list({(r.encounter_id, r.encounter_name) for r in rows})
    name_map = await resolve_encounter_names_with_fallback(
        session, locale=user.locale or locale, encounters=pairs
    )
    out: list[TopLogOut] = []
    for r in rows:
        item = TopLogOut.model_validate(r)
        item.encounter_name_localized = name_map.get(r.encounter_id)
        out.append(item)
    return out


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_top_logs(
    spec_slug: str,
    encounter_id: int,
    session: SessionDep,
    _: AdminUser,
    metric: str | None = Query(default=None, pattern=r"^(dps|hps)$"),
    wcl_flavor: str = Query(default="retail", pattern=r"^(retail|fresh|classic)$"),
) -> dict[str, int]:
    if wcl_flavor == "fresh" and not settings.top_logs_fresh_enabled:
        raise ValidationAppError("Fresh top logs are disabled on this server.")
    spec = (
        await session.execute(select(GameSpec).where(GameSpec.slug == spec_slug))
    ).scalar_one_or_none()
    if not spec:
        raise NotFoundError(f"Unknown spec_slug: {spec_slug}")
    rows = await top_logs_service.refresh_top_logs_for_spec_encounter(
        session,
        spec=spec,
        encounter_id=encounter_id,
        metric=metric,
        wcl_flavor=wcl_flavor,
    )
    await session.commit()
    return {"refreshed": len(rows)}
