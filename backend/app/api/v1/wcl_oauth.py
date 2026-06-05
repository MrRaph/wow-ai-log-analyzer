"""Endpoints implementing the user-side WCL OAuth ``authorization_code`` flow."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.config import settings
from app.deps import CurrentUser, SessionDep
from app.schemas.wcl import WclAuthorizationStart
from app.services import wcl_oauth_service

logger = logging.getLogger(__name__)
router = APIRouter()
router_fresh = APIRouter()


async def _start_wcl_oauth(user: CurrentUser, *, flavor: str) -> WclAuthorizationStart:
    """Return the URL the browser should be redirected to for WCL authorisation."""
    url = wcl_oauth_service.build_authorization_url(user=user, flavor=flavor)
    return WclAuthorizationStart(authorization_url=url, flavor=flavor)


@router.post("/start", response_model=WclAuthorizationStart)
async def start_wcl_oauth(user: CurrentUser) -> WclAuthorizationStart:
    return await _start_wcl_oauth(user, flavor="retail")


@router_fresh.post("/start", response_model=WclAuthorizationStart)
async def start_wcl_oauth_fresh(user: CurrentUser) -> WclAuthorizationStart:
    return await _start_wcl_oauth(user, flavor="fresh")


async def _wcl_oauth_callback(
    session: SessionDep,
    *,
    flavor: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """OAuth redirect target. Exchanges the code, then redirects back to the frontend."""
    base = settings.public_base_url.rstrip("/")

    if error:
        logger.warning("WCL OAuth returned error %s: %s", error, error_description)
        params = urlencode({"wcl": "error", "reason": error})
        return RedirectResponse(url=f"{base}/en/profile?{params}", status_code=302)

    try:
        user = await wcl_oauth_service.handle_callback(
            session,
            code=code or "",
            state=state or "",
            flavor=flavor,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("WCL OAuth callback failed")
        params = urlencode({"wcl": "error", "reason": exc.__class__.__name__})
        return RedirectResponse(url=f"{base}/en/profile?{params}", status_code=302)

    locale = user.locale if user.locale in {"en", "de"} else "en"
    result = "connected-fresh" if flavor == "fresh" else "connected"
    return RedirectResponse(url=f"{base}/{locale}/profile?wcl={result}", status_code=302)


@router.get("/callback", include_in_schema=False)
async def wcl_oauth_callback(
    session: SessionDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    return await _wcl_oauth_callback(
        session,
        flavor="retail",
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )


@router_fresh.get("/callback", include_in_schema=False)
async def wcl_oauth_callback_fresh(
    session: SessionDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    return await _wcl_oauth_callback(
        session,
        flavor="fresh",
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )
