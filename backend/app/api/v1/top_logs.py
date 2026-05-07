"""Endpoints for browsing top logs and (admin) refreshing them."""
from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.core.errors import NotFoundError
from app.deps import AdminUser, CurrentUser, SessionDep
from app.models import GameSpec
from app.schemas.analysis import TopLogOut
from app.services import top_logs_service

router = APIRouter()


@router.get("", response_model=list[TopLogOut])
async def list_top_logs(
    session: SessionDep,
    _: CurrentUser,
    spec_slug: str = Query(..., description="GameSpec slug, e.g. 'priest_holy'"),
    encounter_id: int | None = Query(default=None),
    metric: str | None = Query(default=None, pattern=r"^(dps|hps)$"),
) -> list[TopLogOut]:
    rows = await top_logs_service.list_top_logs(
        session, spec_slug=spec_slug, encounter_id=encounter_id, metric=metric
    )
    return [TopLogOut.model_validate(r) for r in rows]


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_top_logs(
    spec_slug: str,
    encounter_id: int,
    session: SessionDep,
    _: AdminUser,
    metric: str | None = Query(default=None, pattern=r"^(dps|hps)$"),
) -> dict[str, int]:
    spec = (
        await session.execute(select(GameSpec).where(GameSpec.slug == spec_slug))
    ).scalar_one_or_none()
    if not spec:
        raise NotFoundError(f"Unknown spec_slug: {spec_slug}")
    rows = await top_logs_service.refresh_top_logs_for_spec_encounter(
        session, spec=spec, encounter_id=encounter_id, metric=metric
    )
    await session.commit()
    return {"refreshed": len(rows)}
