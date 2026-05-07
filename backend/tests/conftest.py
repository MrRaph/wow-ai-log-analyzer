"""Test fixtures: in-memory SQLite + an app instance for httpx ASGI calls."""
from __future__ import annotations

import os

# Tests must run before app.config is imported the first time, so it picks up
# the in-memory test database.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("WCL_CLIENT_ID", "")
os.environ.setdefault("WCL_CLIENT_SECRET", "")

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db as app_db
from app.main import create_app
from app.models import Base
from app.models import User, UserRole
from app.core.security import hash_password


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:", future=True
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine, monkeypatch) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(app_db, "engine", engine)
    monkeypatch.setattr(app_db, "async_session_factory", factory)
    return factory


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncSession:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(session_factory):
    app = create_app()
    async with LifespanManager(app, startup_timeout=10):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def user(session) -> User:
    u = User(
        email="user@example.com",
        display_name="User",
        password_hash=hash_password("password1234"),
        role=UserRole.user,
        is_active=True,
    )
    session.add(u)
    await session.commit()
    return u


@pytest_asyncio.fixture
async def admin(session) -> User:
    u = User(
        email="admin@example.com",
        display_name="Admin",
        password_hash=hash_password("password1234"),
        role=UserRole.admin,
        is_active=True,
    )
    session.add(u)
    await session.commit()
    return u
