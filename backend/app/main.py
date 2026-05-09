"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.config import assert_production_secrets, settings
from app.core.errors import register_exception_handlers
from app.db import async_session_factory
from app.models import AppSetting
from app.services import local_ai_supervisor_service as supervisor
from app.services.seed import run_all_seeds

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def _resolve_active_ai_provider() -> str:
    """Active provider = DB override (if set) else .env default.

    Mirrors the resolution in :mod:`app.api.v1.admin._settings_value` —
    we re-implement it here to avoid pulling that admin-only helper into
    the lifespan path.
    """
    try:
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(AppSetting).where(AppSetting.key == "ai_provider")
                )
            ).scalar_one_or_none()
            if row and row.value and "value" in row.value:
                return str(row.value["value"])
    except Exception:
        logger.exception("Could not read ai_provider from DB during startup")
    return settings.ai_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to start in production with the placeholder values from
    # .env.example — those would silently expose the app to JWT-forging.
    assert_production_secrets()

    # Seed reference data on every boot. Safe (idempotent) — uses upserts.
    try:
        async with async_session_factory() as session:
            async with session.begin():
                await run_all_seeds(session)
        logger.info("Startup seed complete.")
    except Exception:
        logger.exception("Startup seed failed; the app will continue to boot.")

    # Align the local-ai sidecar's desired-running flag with the admin's
    # chosen provider. Compose's ``restart: unless-stopped`` would
    # otherwise re-spawn the inference child on every host reboot even
    # when the admin has switched away from "local".
    try:
        provider = await _resolve_active_ai_provider()
        await supervisor.ensure_running(provider == "local")
        logger.info("local-ai supervisor aligned with provider=%s", provider)
    except Exception:
        logger.exception("local-ai supervisor alignment failed; continuing")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
