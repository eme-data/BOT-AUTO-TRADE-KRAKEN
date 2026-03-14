"""Integration tests for the dashboard API endpoints.

Tests cover authentication, settings, trades, and AI status endpoints.
All tests use an in-memory SQLite database and do not call external services.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from bot.db.models import Trade


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Auth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Correct credentials return a bearer token."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Wrong password returns 401."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong_password"},
    )
    assert resp.status_code == 401
    assert "Invalid credentials" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_wrong_username(client: AsyncClient):
    """Wrong username returns 401."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "hacker", "password": "admin"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    """Accessing a protected endpoint without a token returns 401."""
    resp = await client.get("/api/trades/")
    assert resp.status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Settings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_settings_schema(client: AsyncClient, auth_headers: dict):
    """GET /api/settings/schema returns a dict of categories with fields."""
    resp = await client.get("/api/settings/schema", headers=auth_headers)
    assert resp.status_code == 200
    schema = resp.json()

    # Must have known categories
    assert "kraken" in schema
    assert "risk" in schema
    assert "notifications" in schema
    assert "ai" in schema

    # Each category contains fields with expected metadata
    kraken = schema["kraken"]
    assert "kraken_api_key" in kraken
    assert "label" in kraken["kraken_api_key"]
    assert "type" in kraken["kraken_api_key"]
    assert "sensitive" in kraken["kraken_api_key"]


@pytest.mark.asyncio
async def test_settings_category_update(client: AsyncClient, auth_headers: dict):
    """PUT /api/settings/category/risk updates risk settings."""
    update_data = {
        "values": {
            "bot_max_daily_loss": "-300",
            "bot_max_open_positions": "3",
        }
    }
    resp = await client.put(
        "/api/settings/category/risk",
        json=update_data,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "updated" in data["message"].lower() or "setting" in data["message"].lower()


@pytest.mark.asyncio
async def test_settings_category_update_unknown_category(
    client: AsyncClient, auth_headers: dict
):
    """PUT to unknown category returns an error message."""
    resp = await client.put(
        "/api/settings/category/nonexistent",
        json={"values": {"foo": "bar"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data or "Unknown category" in str(data)


@pytest.mark.asyncio
async def test_settings_status(client: AsyncClient, auth_headers: dict):
    """GET /api/settings/status returns configuration status."""
    resp = await client.get("/api/settings/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    # Expected fields
    assert "configured" in data
    assert "kraken_connected" in data
    assert "telegram_configured" in data
    assert "acc_type" in data
    assert "categories" in data
    assert isinstance(data["categories"], dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Trades
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_trades_list_empty(client: AsyncClient, auth_headers: dict):
    """GET /api/trades/ returns an empty list when no trades exist."""
    resp = await client.get("/api/trades/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_trades_list_with_data(
    client: AsyncClient, auth_headers: dict, db_session
):
    """GET /api/trades/ returns trades when they exist in DB."""
    # Insert a trade directly via the session
    trade = Trade(
        order_id="INT-TEST-001",
        pair="BTC/USD",
        direction="buy",
        size=0.05,
        entry_price=50_000.0,
        status="OPEN",
        strategy="macd_trend",
        opened_at=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.get("/api/trades/", headers=auth_headers)
    assert resp.status_code == 200
    trades = resp.json()
    assert len(trades) >= 1
    assert trades[0]["pair"] == "BTC/USD"
    assert trades[0]["order_id"] == "INT-TEST-001"
    assert trades[0]["direction"] == "buy"


@pytest.mark.asyncio
async def test_trades_open_endpoint(
    client: AsyncClient, auth_headers: dict, db_session
):
    """GET /api/trades/open returns only open trades."""
    open_trade = Trade(
        order_id="OPEN-001",
        pair="ETH/USD",
        direction="buy",
        size=1.0,
        entry_price=3_000.0,
        status="OPEN",
        strategy="rsi",
        opened_at=datetime.now(timezone.utc),
    )
    closed_trade = Trade(
        order_id="CLOSED-001",
        pair="BTC/USD",
        direction="sell",
        size=0.01,
        entry_price=55_000.0,
        exit_price=54_000.0,
        profit=10.0,
        status="CLOSED",
        strategy="macd_trend",
        opened_at=datetime.now(timezone.utc),
        closed_at=datetime.now(timezone.utc),
    )
    db_session.add(open_trade)
    db_session.add(closed_trade)
    await db_session.commit()

    resp = await client.get("/api/trades/open", headers=auth_headers)
    assert resp.status_code == 200
    trades = resp.json()
    assert len(trades) == 1
    assert trades[0]["order_id"] == "OPEN-001"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI Status
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_ai_status(client: AsyncClient, auth_headers: dict):
    """GET /api/ai/status returns AI configuration status."""
    resp = await client.get("/api/ai/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "enabled" in data
    assert "configured" in data
    assert "model" in data
    assert "modes" in data
    assert isinstance(data["modes"], dict)
    assert "pre_trade" in data["modes"]
    assert "market_review" in data["modes"]
    assert "sentiment" in data["modes"]
    assert "post_trade" in data["modes"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Health check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """GET /api/health returns ok (no auth required)."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
