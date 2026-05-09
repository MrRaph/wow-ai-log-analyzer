"""Test fixtures: an app instance + a database for httpx ASGI calls.

Database selection (in priority order):

1. ``TEST_DATABASE_URL`` — explicit override, highest priority.
2. ``DATABASE_URL`` — implicit if set (CI typically does).
3. Otherwise: SQLite in-memory — fast for local iteration, but doesn't
   exercise Postgres-only features (UUID native type, JSONB indexing).
   CI uses real Postgres so the full schema is verified there.

Run locally against the compose Postgres for a full-fidelity test run::

    docker compose exec backend uv run pytest
"""
from __future__ import annotations

import os

# These must be set before app.config is imported so settings pick them
# up rather than the .env defaults.
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


def _resolve_test_db_url() -> str:
    """Pick the database the test session should run against."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    fallback_env = os.environ.get("DATABASE_URL")
    if fallback_env:
        # Coerce ``postgresql://`` to the asyncpg driver so SQLAlchemy's
        # async engine accepts it without further config.
        return fallback_env.replace("postgresql://", "postgresql+asyncpg://", 1)
    return "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    url = _resolve_test_db_url()
    eng = create_async_engine(url, future=True)
    # Drop-and-recreate keeps each test session deterministic when
    # running against a real Postgres (in-memory SQLite is naturally
    # fresh on every fixture invocation).
    async with eng.begin() as conn:
        if not url.startswith("sqlite"):
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    if not url.startswith("sqlite"):
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
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
