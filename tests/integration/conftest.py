"""Shared fixtures for integration tests.

- In-memory SQLite database via aiosqlite
- FastAPI test app with overridden DB session dependency
- Auth token fixture for authenticated requests
- Mock broker fixture
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.broker.models import AccountBalance, Direction, Position
from bot.db.models import Base


# ── In-memory test database ──────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DB_URL, echo=False)
_test_session_factory = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Fixtures ─────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _setup_test_db():
    """Create all tables before each test and drop them after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a raw async session for direct DB manipulation in tests."""
    async with _test_session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def test_app():
    """Return a FastAPI app with the DB session dependency overridden."""
    # Patch get_session *before* importing routers that use it at call time
    import bot.db.session as session_mod
    original = session_mod.get_session
    session_mod.get_session = _override_get_session

    # Import the app (routers reference get_session at call time, not import)
    from dashboard.api.main import app

    yield app

    # Restore
    session_mod.get_session = original


@pytest_asyncio.fixture
async def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound to the test FastAPI app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient) -> str:
    """Obtain a valid JWT token by logging in with default admin credentials."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict[str, str]:
    """Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
def mock_broker():
    """A mock broker that avoids real Kraken API calls."""
    broker = AsyncMock()
    broker.connect = AsyncMock()
    broker.disconnect = AsyncMock()

    # Default balance
    broker.get_balance = AsyncMock(
        return_value=AccountBalance(
            total_balance=10_000.0,
            available_balance=8_000.0,
            margin_used=2_000.0,
            unrealized_pnl=50.0,
            currency="USD",
        )
    )

    # No open positions by default
    broker.get_positions = AsyncMock(return_value=[])

    # Successful order placement
    from bot.broker.models import OrderResult, OrderStatus
    from datetime import datetime, timezone

    broker.place_order = AsyncMock(
        return_value=OrderResult(
            order_id="TEST-ORDER-001",
            pair="BTC/USD",
            direction=Direction.BUY,
            size=0.01,
            price=50_000.0,
            status=OrderStatus.CLOSED,
            timestamp=datetime.now(timezone.utc),
            fee=0.26,
        )
    )

    return broker
