"""AI Market Journal – daily AI-generated crypto market summaries."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from bot.ai.analyzer import ClaudeAnalyzer
from bot.config import settings
from bot.db.repository import MarketJournalRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/market-journal",
    tags=["market-journal"],
    dependencies=[Depends(get_current_user)],
)


def _entry_dict(e) -> dict:
    return {
        "id": e.id,
        "date": e.date.isoformat() if e.date else None,
        "summary": e.summary,
        "sentiment": e.sentiment,
        "key_events": e.key_events,
        "market_data": e.market_data,
        "model_used": e.model_used,
    }


@router.get("/")
async def get_journal_entries(
    limit: int = Query(30, ge=1, le=200),
    user_id: int = Depends(get_user_id),
):
    """Get recent market journal entries."""
    async with get_session() as session:
        repo = MarketJournalRepository(session, user_id=user_id)
        entries = await repo.get_recent(limit=limit)
        return [_entry_dict(e) for e in entries]


@router.post("/generate")
async def generate_journal(user_id: int = Depends(get_user_id)):
    """Generate today's AI market journal using live crypto prices."""
    from bot.crypto import decrypt
    from bot.db.repository import SettingsRepository

    # Load fresh AI settings from DB
    ai_enabled = settings.ai_enabled
    ai_api_key = settings.ai_api_key
    try:
        async with get_session() as session:
            repo = SettingsRepository(session, user_id=user_id)
            db_values = await repo.get_decrypted_values(decrypt)
            if db_values:
                if "ai_enabled" in db_values:
                    ai_enabled = str(db_values["ai_enabled"]).lower() in (
                        "true", "1", "yes", "on",
                    )
                if "ai_api_key" in db_values:
                    ai_api_key = db_values["ai_api_key"]
                settings.apply_db_overrides(db_values)
    except Exception:
        pass

    if not ai_enabled or not ai_api_key:
        return {"error": "AI non configure. Activez-le dans les parametres."}

    # Fetch live prices for top pairs
    from bot.broker.kraken_rest import KrakenRestClient

    top_pairs = [
        "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD",
        "DOT/USD", "AVAX/USD", "LINK/USD", "ATOM/USD", "DOGE/USD",
    ]

    prices_data: dict[str, dict] = {}
    broker = KrakenRestClient()
    await broker.connect()
    try:
        for pair in top_pairs:
            try:
                tick = await broker.get_ticker(pair)
                prices_data[pair] = {
                    "last": tick.last,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "volume": tick.volume,
                }
            except Exception:
                pass
    finally:
        await broker.disconnect()

    if not prices_data:
        return {"error": "Impossible de recuperer les prix du marche."}

    # Format prices for prompt
    prices_text = "\n".join(
        f"- {pair}: ${data['last']:,.2f} (volume: {data['volume']:,.0f})"
        for pair, data in prices_data.items()
    )

    prompt = (
        "Genere un resume quotidien du marche crypto. "
        "Inclus: tendances principales, evenements cles, sentiment general "
        "(bullish/bearish/neutral), et perspectives.\n\n"
        f"Donnees actuelles du marche:\n{prices_text}\n\n"
        "Reponds en JSON avec cette structure exacte:\n"
        "```json\n"
        "{\n"
        '  "summary": "Resume detaille du marche (3-5 paragraphes en francais)",\n'
        '  "sentiment": "bullish" | "bearish" | "neutral",\n'
        '  "key_events": ["Evenement 1", "Evenement 2", ...]\n'
        "}\n"
        "```"
    )

    analyzer = ClaudeAnalyzer()
    try:
        raw_response = await analyzer._call_claude(prompt)
    except Exception as exc:
        return {"error": f"Erreur AI: {exc}"}
    finally:
        await analyzer.close()

    # Parse AI response
    summary = raw_response
    sentiment = "neutral"
    key_events: list[str] = []

    try:
        json_str = raw_response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        parsed = json.loads(json_str)
        summary = parsed.get("summary", raw_response)
        sentiment = parsed.get("sentiment", "neutral")
        if sentiment not in ("bullish", "bearish", "neutral"):
            sentiment = "neutral"
        key_events = parsed.get("key_events", [])
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Save to DB
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        repo = MarketJournalRepository(session, user_id=user_id)
        entry = await repo.save(
            date=now,
            summary=summary,
            sentiment=sentiment,
            key_events=key_events,
            market_data=prices_data,
            model_used=settings.ai_model,
        )
        await session.commit()
        return _entry_dict(entry)


@router.get("/latest")
async def get_latest_entry(user_id: int = Depends(get_user_id)):
    """Get the most recent market journal entry."""
    async with get_session() as session:
        repo = MarketJournalRepository(session, user_id=user_id)
        entries = await repo.get_recent(limit=1)
        if not entries:
            return None
        return _entry_dict(entries[0])
