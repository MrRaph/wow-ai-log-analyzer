"""Seed static data on app startup (classes/specs, default settings, initial admin)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.models import AppSetting, GameClass, GameSpec, Role, User, UserRole

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"


async def seed_classes_and_specs(session: AsyncSession) -> None:
    payload = json.loads((_DATA_DIR / "classes_specs.json").read_text(encoding="utf-8"))
    classes = payload["classes"]
    specs = payload["specs"]

    if classes:
        stmt = pg_insert(GameClass).values(classes)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GameClass.slug],
            set_={"name_en": stmt.excluded.name_en, "name_de": stmt.excluded.name_de, "color_hex": stmt.excluded.color_hex},
        )
        await session.execute(stmt)

    if specs:
        normalised = [{**s, "role": Role(s["role"]).value} for s in specs]
        stmt = pg_insert(GameSpec).values(normalised)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GameSpec.slug],
            set_={
                "class_slug": stmt.excluded.class_slug,
                "name_en": stmt.excluded.name_en,
                "name_de": stmt.excluded.name_de,
                "role": stmt.excluded.role,
                "wcl_spec_id": stmt.excluded.wcl_spec_id,
            },
        )
        await session.execute(stmt)


async def seed_default_settings(session: AsyncSession) -> None:
    defaults = {
        "allow_registration": {"enabled": settings.allow_registration},
        "ai_provider": {"value": settings.ai_provider},
        "ai_model": {"value": settings.ai_model},
    }
    for key, value in defaults.items():
        stmt = pg_insert(AppSetting).values(key=key, value=value)
        stmt = stmt.on_conflict_do_nothing(index_elements=[AppSetting.key])
        await session.execute(stmt)


async def seed_initial_admin(session: AsyncSession) -> None:
    existing = await session.execute(select(User).where(User.role == UserRole.admin))
    if existing.first():
        return
    admin = User(
        email=str(settings.initial_admin_email),
        display_name="Administrator",
        password_hash=hash_password(settings.initial_admin_password),
        role=UserRole.admin,
        is_active=True,
        locale="en",
    )
    session.add(admin)
    logger.info("Created initial admin: %s", settings.initial_admin_email)


async def run_all_seeds(session: AsyncSession) -> None:
    await seed_classes_and_specs(session)
    await seed_default_settings(session)
    await seed_initial_admin(session)
