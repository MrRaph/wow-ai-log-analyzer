"""Endpoints for importing + browsing reports."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.deps import CurrentUser, SessionDep
from app.models import Report, ReportFight, ReportPlayer
from app.schemas.report import ReportImportIn, ReportOut, ReportSummaryOut
from app.services import report_service

router = APIRouter()


@router.post("/import", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def import_report(
    payload: ReportImportIn, session: SessionDep, user: CurrentUser
) -> ReportOut:
    report = await report_service.import_report(
        session, raw_input=payload.wcl_url_or_code, owner_user_id=user.id
    )
    await session.commit()
    return ReportOut.model_validate(report)


@router.get("", response_model=list[ReportSummaryOut])
async def list_my_reports(session: SessionDep, user: CurrentUser) -> list[ReportSummaryOut]:
    rows = (
        await session.execute(
            select(Report)
            .where(Report.owner_user_id == user.id)
            .order_by(Report.start_time.desc())
            .limit(50)
        )
    ).scalars().all()
    return [ReportSummaryOut.model_validate(r) for r in rows]


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> ReportOut:
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
    return ReportOut.model_validate(report)


@router.get("/by-code/{code}", response_model=ReportOut)
async def get_report_by_code(code: str, session: SessionDep, _: CurrentUser) -> ReportOut:
    report = await report_service.get_report(session, code=code)
    return ReportOut.model_validate(report)
