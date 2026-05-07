"""Admin-only endpoints: settings, invites, user management."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.core.errors import NotFoundError
from app.deps import AdminUser, SessionDep
from app.models import AppSetting, Invite, User
from app.schemas.user import (
    AdminSettingsOut,
    AdminSettingsUpdate,
    AdminUserUpdate,
    InviteIn,
    InviteOut,
    UserOut,
)
from app.services import auth_service

router = APIRouter()


# --- App settings -------------------------------------------------------------


def _settings_value(rows: list[AppSetting], key: str, default: object) -> object:
    for r in rows:
        if r.key == key:
            return (r.value or {}).get("value", (r.value or {}).get("enabled", default))
    return default


@router.get("/settings", response_model=AdminSettingsOut)
async def read_settings(session: SessionDep, _: AdminUser) -> AdminSettingsOut:
    rows = (await session.execute(select(AppSetting))).scalars().all()
    return AdminSettingsOut(
        allow_registration=bool(_settings_value(rows, "allow_registration", settings.allow_registration)),
        ai_provider=str(_settings_value(rows, "ai_provider", settings.ai_provider)),
        ai_model=str(_settings_value(rows, "ai_model", settings.ai_model)),
    )


async def _upsert_setting(session, key: str, value: dict) -> None:
    stmt = pg_insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": stmt.excluded.value})
    await session.execute(stmt)


@router.patch("/settings", response_model=AdminSettingsOut)
async def update_settings(
    payload: AdminSettingsUpdate, session: SessionDep, _: AdminUser
) -> AdminSettingsOut:
    if payload.allow_registration is not None:
        await _upsert_setting(session, "allow_registration", {"enabled": payload.allow_registration})
    if payload.ai_provider is not None:
        await _upsert_setting(session, "ai_provider", {"value": payload.ai_provider})
    if payload.ai_model is not None:
        await _upsert_setting(session, "ai_model", {"value": payload.ai_model})
    await session.commit()
    return await read_settings(session, _)


# --- Invites ------------------------------------------------------------------


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(session: SessionDep, _: AdminUser) -> list[InviteOut]:
    rows = (
        await session.execute(select(Invite).order_by(Invite.created_at.desc()))
    ).scalars().all()
    return [InviteOut.model_validate(r) for r in rows]


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def create_invite(payload: InviteIn, session: SessionDep, admin: AdminUser) -> InviteOut:
    invite = await auth_service.create_invite(
        session, email=payload.email, inviter=admin, locale=payload.locale
    )
    await session.commit()
    return InviteOut.model_validate(invite)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: uuid.UUID, session: SessionDep, _: AdminUser) -> None:
    await auth_service.revoke_invite(session, invite_id)
    await session.commit()


# --- Users --------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
async def list_users(session: SessionDep, _: AdminUser) -> list[UserOut]:
    rows = (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, payload: AdminUserUpdate, session: SessionDep, _: AdminUser
) -> UserOut:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found.")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await session.commit()
    return UserOut.model_validate(user)
