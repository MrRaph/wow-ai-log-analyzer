"""Anonymous read of an analysis by its share token. No auth required.

Lives on its own router (and its own URL prefix) instead of under the
authenticated ``/analyses`` namespace so the token-based path can't
collide with the UUID-based ``/analyses/{analysis_id}`` route — that one
runs UUID validation on the path param and we don't want a stray
``shared`` segment getting routed through it.

The actual handler logic lives in ``app.api.v1.analysis`` so the
owner-side endpoints and the public read share one source of truth for
the row → schema mapping.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.analysis import fetch_shared_analysis
from app.deps import LocaleDep, SessionDep
from app.schemas.analysis import AnalysisPublicOut

router = APIRouter()


@router.get("/{share_token}", response_model=AnalysisPublicOut)
async def get_shared_analysis(
    share_token: str, session: SessionDep, locale: LocaleDep
) -> AnalysisPublicOut:
    return await fetch_shared_analysis(share_token, session, locale)
