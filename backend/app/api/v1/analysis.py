"""Endpoints for AI analyses."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.errors import NotFoundError
from app.deps import CurrentUser, LocaleDep, SessionDep
from app.models import Analysis
from app.schemas.analysis import AnalysisIn, AnalysisOut
from app.services.ai import analyzer

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
    return AnalysisOut.model_validate(analysis)


@router.get("/{analysis_id}", response_model=AnalysisOut)
async def get_analysis(analysis_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> AnalysisOut:
    row = (
        await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Analysis not found.")
    return AnalysisOut.model_validate(row)
