"""Market info, prices, and watchlist endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bot.broker.kraken_rest import KrakenRestClient
from bot.config import settings
from bot.db.repository import WatchlistRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user

router = APIRouter(
    prefix="/api/markets",
    tags=["markets"],
    dependencies=[Depends(get_current_user)],
)


async def _get_connected_broker() -> KrakenRestClient:
    """Create a broker with fresh DB credentials."""
    from bot.crypto import decrypt
    from bot.db.repository import SettingsRepository

    try:
        async with get_session() as session:
            repo = SettingsRepository(session)
            db_values = await repo.get_decrypted_values(decrypt)
    except Exception:
        db_values = {}

    api_key = db_values.get("kraken_api_key", settings.kraken_api_key)
    api_secret = db_values.get("kraken_api_secret", settings.kraken_api_secret)

    if api_key:
        object.__setattr__(settings, "kraken_api_key", api_key)
    if api_secret:
        object.__setattr__(settings, "kraken_api_secret", api_secret)
    # Always force LIVE for real API calls (DEMO uses PaperBroker)
    object.__setattr__(settings, "kraken_acc_type", "LIVE")

    broker = KrakenRestClient()
    await broker.connect()
    return broker


class WatchlistAdd(BaseModel):
    pair: str


@router.get("/pairs")
async def tradeable_pairs():
    broker = await _get_connected_broker()
    try:
        pairs = await broker.get_tradeable_pairs()
        return pairs[:100]
    finally:
        await broker.disconnect()


@router.get("/prices")
async def crypto_prices():
    """Get real-time prices for major crypto pairs."""
    target_pairs = [
        "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD",
        "ADA/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
        "MATIC/USD", "ATOM/USD",
    ]

    broker = await _get_connected_broker()
    try:
        results = []
        for pair in target_pairs:
            try:
                tick = await broker.get_ticker(pair)
                results.append({
                    "pair": pair,
                    "last": tick.last,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread": round(tick.spread, 6),
                    "volume": tick.volume,
                })
            except Exception:
                pass  # Skip pairs not available
        return results
    finally:
        await broker.disconnect()


@router.get("/watchlist")
async def get_watchlist():
    async with get_session() as session:
        repo = WatchlistRepository(session)
        markets = await repo.get_active()
        return [{"pair": m.pair, "active": m.active} for m in markets]


@router.post("/watchlist")
async def add_to_watchlist(body: WatchlistAdd):
    async with get_session() as session:
        repo = WatchlistRepository(session)
        await repo.add(body.pair)
        return {"message": f"{body.pair} added to watchlist"}


@router.delete("/watchlist/{pair}")
async def remove_from_watchlist(pair: str):
    async with get_session() as session:
        repo = WatchlistRepository(session)
        await repo.remove(pair)
        return {"message": f"{pair} removed from watchlist"}
