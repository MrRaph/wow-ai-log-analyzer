"""Endpoints for importing + browsing reports."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.errors import ForbiddenError, NotFoundError
from app.deps import ArqDep, CurrentUser, LocaleDep, SessionDep
from app.models import Report, ReportFight, ReportPlayer, UserRole
from app.schemas.report import (
    PaginatedReports,
    ReportImportIn,
    ReportOut,
    ReportSummaryOut,
)
from app.services import report_service
from app.services.wow_data_service import resolve_encounter_names_with_fallback

router = APIRouter()


async def _localize_fight_names(
    session: "SessionDep", report: Report, locale: str
) -> dict[int, str]:
    pairs = [
        (int(f.encounter_id), str(f.name or ""))
        for f in report.fights
        if f.encounter_id
    ]
    if not pairs:
        return {}
    return await resolve_encounter_names_with_fallback(
        session, locale=locale, encounters=pairs
    )


def _serialize_report(report: Report, encounter_name_map: dict[int, str]) -> ReportOut:
    out = ReportOut.model_validate(report)
    for fight in out.fights:
        if fight.encounter_id and fight.encounter_id in encounter_name_map:
            fight.name_localized = encounter_name_map[fight.encounter_id]
    return out


@router.post("/import", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
async def import_report(
    payload: ReportImportIn,
    session: SessionDep,
    user: CurrentUser,
    locale: LocaleDep,
    arq: ArqDep,
) -> ReportOut:
    """Create a skeleton Report row and enqueue the worker to populate it.

    Returns 202 Accepted with the row in ``import_status="importing"``.
    The frontend polls ``GET /reports/{id}`` until ``import_status`` flips
    to ``ready`` (or ``failed`` with ``import_error``).
    """
    report = await report_service.create_import_skeleton(
        session,
        raw_input=payload.wcl_url_or_code,
        owner_user_id=user.id,
    )
    # If a previous attempt failed, allow re-trigger by flipping back to
    # importing on the same row before enqueueing.
    if report.import_status == "failed":
        report.import_status = "importing"
        report.import_error = None
    await session.commit()
    # Eager-load the fights relationship explicitly. After commit, SQLAlchemy
    # expires every attribute on the row, so the next pydantic access would
    # trigger a sync IO lazy-load (→ MissingGreenlet under asyncpg). On a
    # skeleton this just resolves to ``[]``; on a re-imported existing row
    # it pulls the previously-cached fights in one query.
    await session.refresh(report, attribute_names=["fights"])

    if report.import_status == "importing":
        await arq.enqueue_job("import_report_task", str(report.id))
        return _serialize_report(report, {})

    name_map = await _localize_fight_names(session, report, user.locale or locale)
    return _serialize_report(report, name_map)


@router.get("", response_model=PaginatedReports)
async def list_my_reports(
    session: SessionDep,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> PaginatedReports:
    base = select(Report).where(Report.owner_user_id == user.id)
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Report.start_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return PaginatedReports(
        items=[ReportSummaryOut.model_validate(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    """Delete a report. Cascades to fights, players, gear, casts and any
    analyses derived from it (FK constraints have ``ON DELETE CASCADE``)."""
    row = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Report not found.")
    if row.owner_user_id != user.id and user.role != UserRole.admin:
        raise ForbiddenError("You can only delete your own reports.")
    await session.delete(row)
    await session.commit()


def _assert_report_visible(report: Report, user) -> None:
    """Owner-or-admin gate. Raises NotFoundError (not Forbidden) on mismatch
    so we don't leak whether a given report id/code exists at all."""
    if report.owner_user_id != user.id and user.role != UserRole.admin:
        raise NotFoundError("Report not found.")


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: uuid.UUID, session: SessionDep, user: CurrentUser, locale: LocaleDep
) -> ReportOut:
    stmt = (
        select(Report)
        .where(Report.id == report_id)
        .options(
            selectinload(Report.fights)
            .selectinload(ReportFight.players)
            .selectinload(ReportPlayer.casts),
            selectinload(Report.fights)
            .selectinload(ReportFight.players)
            .selectinload(ReportPlayer.gear),
        )
    )
    report = (await session.execute(stmt)).scalar_one_or_none()
    if not report:
        raise NotFoundError("Report not found.")
    _assert_report_visible(report, user)
    name_map = await _localize_fight_names(session, report, user.locale or locale)
    return _serialize_report(report, name_map)


@router.get("/by-code/{code}", response_model=ReportOut)
async def get_report_by_code(
    code: str, session: SessionDep, user: CurrentUser, locale: LocaleDep
) -> ReportOut:
    report = await report_service.get_report(session, code=code)
    _assert_report_visible(report, user)
    name_map = await _localize_fight_names(session, report, user.locale or locale)
    return _serialize_report(report, name_map)
