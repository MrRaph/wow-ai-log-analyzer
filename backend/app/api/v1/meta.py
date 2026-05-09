"""Meta endpoints: health check, public app config, classes/specs reference."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.config import settings
from app.deps import SessionDep
from app.models import AppSetting, GameClass, GameSpec

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config")
async def public_config(session: SessionDep) -> dict[str, object]:
    """Configuration the frontend needs *before* a user is logged in."""
    rows = (await session.execute(select(AppSetting))).scalars().all()
    cfg = {row.key: row.value for row in rows}
    allow_reg_value = cfg.get("allow_registration") or {}
    ai_provider_value = cfg.get("ai_provider") or {}
    active_ai = ai_provider_value.get("value") or settings.ai_provider
    return {
        "app_name": settings.app_name,
        "supported_locales": ["en", "de"],
        "allow_registration": bool(allow_reg_value.get("enabled", settings.allow_registration)),
        # ``ai_enabled = false`` → admin set ``ai_provider=disabled``.
        # Frontend uses this to grey out the "Analyze with app AI" button.
        "ai_enabled": active_ai != "disabled",
        "captcha_enabled": settings.turnstile_enabled,
    }


@router.get("/classes")
async def list_classes(session: SessionDep) -> list[dict[str, object]]:
    classes = (await session.execute(select(GameClass).order_by(GameClass.slug))).scalars().all()
    specs = (await session.execute(select(GameSpec).order_by(GameSpec.slug))).scalars().all()
    by_class: dict[str, list[dict[str, object]]] = {}
    for s in specs:
        by_class.setdefault(s.class_slug, []).append(
            {
                "slug": s.slug,
                "name_en": s.name_en,
                "name_de": s.name_de,
                "role": s.role.value,
                "wcl_spec_id": s.wcl_spec_id,
            }
        )
    return [
        {
            "slug": c.slug,
            "name_en": c.name_en,
            "name_de": c.name_de,
            "color_hex": c.color_hex,
            "specs": by_class.get(c.slug, []),
        }
        for c in classes
    ]
