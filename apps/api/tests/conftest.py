"""Pytest fixtures — uses an in-memory SQLite for tests (no Postgres dependency)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# secrets must be set BEFORE settings is imported
os.environ.setdefault("COBWEB_SECRET_KEY", "test-secret-test-secret-test-secret-1234")
os.environ.setdefault("COBWEB_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from cobweb.db.base import Base, get_db  # noqa: E402
from cobweb.main import app  # noqa: E402
from cobweb.api.v1 import scans as scans_router  # noqa: E402
from cobweb.services import scan_orchestrator  # noqa: E402


@pytest.fixture(autouse=True)
def stub_external(monkeypatch):
    """Replace RabbitMQ publish + Redis publish with no-ops in tests."""

    class _StubPublisher:
        async def connect(self):
            return None

        async def publish(self, *_args, **_kwargs):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(scan_orchestrator, "get_publisher", lambda: _StubPublisher())

    async def _no_publish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(scan_orchestrator, "publish_scan_event", _no_publish)
    monkeypatch.setattr(scans_router, "publish_scan_event", _no_publish)
    yield


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncIterator[AsyncClient]:
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
