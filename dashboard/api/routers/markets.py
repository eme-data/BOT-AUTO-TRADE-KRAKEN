"""Market info and watchlist endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bot.broker.kraken_rest import KrakenRestClient
from bot.db.repository import WatchlistRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user

router = APIRouter(
    prefix="/api/markets",
    tags=["markets"],
    dependencies=[Depends(get_current_user)],
)


class WatchlistAdd(BaseModel):
    pair: str


@router.get("/pairs")
async def tradeable_pairs():
    broker = KrakenRestClient()
    try:
        await broker.connect()
        pairs = await broker.get_tradeable_pairs()
        return pairs[:100]  # limit response size
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
