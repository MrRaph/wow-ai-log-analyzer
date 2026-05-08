"""Auth-related endpoints: register, login, refresh, password reset, accept invite."""
from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.deps import LocaleDep, SessionDep
from app.schemas.auth import (
    AcceptInviteIn,
    LoginIn,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshIn,
    RegisterIn,
    TokenPair,
)
from app.schemas.user import UserOut
from app.services import auth_service, captcha

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    # Prefer X-Forwarded-For when behind a reverse proxy (uvicorn started with
    # --proxy-headers). Falls back to the direct socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else None


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, session: SessionDep, request: Request) -> TokenPair:
    await captcha.verify_or_raise(payload.captcha_token, remote_ip=_client_ip(request))
    user = await auth_service.register_user(
        session,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        invite_token=payload.invite_token,
    )
    await session.commit()
    return TokenPair(**auth_service.issue_token_pair(user))


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginIn, session: SessionDep, request: Request) -> TokenPair:
    await captcha.verify_or_raise(payload.captcha_token, remote_ip=_client_ip(request))
    user = await auth_service.authenticate(session, email=payload.email, password=payload.password)
    await session.commit()
    return TokenPair(**auth_service.issue_token_pair(user))


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshIn, session: SessionDep) -> TokenPair:
    tokens = await auth_service.refresh_tokens(session, payload.refresh_token)
    return TokenPair(**tokens)


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset_request(
    payload: PasswordResetRequest,
    session: SessionDep,
    locale: LocaleDep,
    request: Request,
) -> None:
    await captcha.verify_or_raise(payload.captcha_token, remote_ip=_client_ip(request))
    await auth_service.initiate_password_reset(session, payload.email, locale)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset_confirm(payload: PasswordResetConfirm, session: SessionDep) -> None:
    await auth_service.confirm_password_reset(session, payload.token, payload.new_password)
    await session.commit()


@router.post("/accept-invite", response_model=UserOut)
async def accept_invite(
    payload: AcceptInviteIn, session: SessionDep, request: Request
) -> UserOut:
    await captcha.verify_or_raise(payload.captcha_token, remote_ip=_client_ip(request))
    user = await auth_service.accept_invite(
        session,
        token=payload.token,
        password=payload.password,
        display_name=payload.display_name,
    )
    await session.commit()
    return UserOut.model_validate(user)
