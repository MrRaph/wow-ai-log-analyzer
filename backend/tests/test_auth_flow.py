"""End-to-end auth flow tests against the running ASGI app."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_register_and_login_flow(client, session):
    # Open registration is enabled by default in tests.
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "verysecret1", "display_name": "New User"},
    )
    assert r.status_code == 201, r.text
    tokens = r.json()
    assert "access_token" in tokens

    # /users/me with the access token returns the user record.
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "newuser@example.com"

    # Login again with the same credentials.
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@example.com", "password": "verysecret1"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_admin_endpoint_requires_admin(client, user):
    # Login as the regular user.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "password1234"},
    )
    assert login.status_code == 200
    tok = login.json()["access_token"]
    r = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_users(client, admin):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "password1234"},
    )
    tok = login.json()["access_token"]
    r = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert any(u["email"] == admin.email for u in body)
