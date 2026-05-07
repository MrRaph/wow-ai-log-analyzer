"""User-self endpoints (/users/me)."""
from __future__ import annotations

from fastapi import APIRouter, status

from app.core.errors import AuthError, ValidationAppError
from app.core.security import hash_password, verify_password
from app.deps import CurrentUser, SessionDep
from app.schemas.user import UserOut, UserUpdateMe

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(payload: UserUpdateMe, user: CurrentUser, session: SessionDep) -> UserOut:
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.locale is not None:
        user.locale = payload.locale
    if payload.new_password is not None:
        if not payload.current_password:
            raise ValidationAppError("Current password is required to change the password.")
        if not verify_password(payload.current_password, user.password_hash):
            raise AuthError("Current password is incorrect.")
        user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return UserOut.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, session: SessionDep) -> None:
    user.is_active = False
    await session.commit()
