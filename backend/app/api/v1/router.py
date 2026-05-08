"""Aggregated v1 router."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analysis,
    auth,
    meta,
    reports,
    top_logs,
    users,
    wcl_oauth,
    wow_data,
)

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(wcl_oauth.router, prefix="/auth/wcl", tags=["auth-wcl"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(wow_data.router, prefix="/admin", tags=["admin-wow-data"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(top_logs.router, prefix="/top-logs", tags=["top-logs"])
api_router.include_router(analysis.router, prefix="/analyses", tags=["analyses"])
