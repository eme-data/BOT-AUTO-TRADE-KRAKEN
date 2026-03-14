"""AI Analysis endpoints – view logs, trigger reviews, check status."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bot.ai.analyzer import ClaudeAnalyzer
from bot.ai.models import AnalysisMode, AIAnalysisRequest
from bot.config import settings
from bot.db.repository import AIAnalysisRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(get_current_user)],
)


# ── Status ─────────────────────────────────────────────

@router.get("/status")
async def ai_status(user_id: int = Depends(get_user_id)):
    """Check if AI is configured and enabled – reads from DB for fresh values."""
    from bot.crypto import decrypt
    from bot.db.repository import SettingsRepository
    from bot.db.session import get_session as _get_session

    # Read fresh values from DB so we don't rely on stale in-memory settings
    ai_enabled = settings.ai_enabled
    ai_api_key = settings.ai_api_key
    ai_model = settings.ai_model
    ai_pre_trade = settings.ai_pre_trade_enabled
    ai_market_review = settings.ai_market_review_enabled
    ai_sentiment = settings.ai_sentiment_enabled
    ai_post_trade = settings.ai_post_trade_enabled

    try:
        async with _get_session() as session:
            repo = SettingsRepository(session, user_id=user_id)
            db_values = await repo.get_decrypted_values(decrypt)
            if db_values:
                ai_enabled = str(db_values.get("ai_enabled", "")).lower() in ("true", "1", "yes", "on") if "ai_enabled" in db_values else ai_enabled
                ai_api_key = db_values.get("ai_api_key", ai_api_key)
                ai_model = db_values.get("ai_model", ai_model)
                ai_pre_trade = str(db_values.get("ai_pre_trade_enabled", "")).lower() in ("true", "1", "yes", "on") if "ai_pre_trade_enabled" in db_values else ai_pre_trade
                ai_market_review = str(db_values.get("ai_market_review_enabled", "")).lower() in ("true", "1", "yes", "on") if "ai_market_review_enabled" in db_values else ai_market_review
                ai_sentiment = str(db_values.get("ai_sentiment_enabled", "")).lower() in ("true", "1", "yes", "on") if "ai_sentiment_enabled" in db_values else ai_sentiment
                ai_post_trade = str(db_values.get("ai_post_trade_enabled", "")).lower() in ("true", "1", "yes", "on") if "ai_post_trade_enabled" in db_values else ai_post_trade
    except Exception:
        pass  # Fall back to in-memory settings

    return {
        "enabled": ai_enabled,
        "configured": bool(ai_api_key),
        "model": ai_model,
        "modes": {
            "pre_trade": ai_pre_trade,
            "market_review": ai_market_review,
            "sentiment": ai_sentiment,
            "post_trade": ai_post_trade,
        },
    }


# ── Analysis logs ──────────────────────────────────────

@router.get("/logs")
async def get_logs(limit: int = 50, user_id: int = Depends(get_user_id)):
    """Get recent AI analysis logs."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session, user_id=user_id)
        logs = await repo.get_recent(limit=limit)
        return [
            {
                "id": l.id,
                "pair": l.pair,
                "mode": l.mode,
                "verdict": l.verdict,
                "confidence": l.confidence,
                "reasoning": l.reasoning,
                "market_summary": l.market_summary,
                "risk_warnings": l.risk_warnings,
                "suggested_adjustments": l.suggested_adjustments,
                "signal_direction": l.signal_direction,
                "signal_strategy": l.signal_strategy,
                "model_used": l.model_used,
                "latency_ms": l.latency_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]


@router.get("/logs/{pair}")
async def get_logs_by_pair(pair: str, limit: int = 20, user_id: int = Depends(get_user_id)):
    """Get AI analysis logs for a specific pair."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session, user_id=user_id)
        logs = await repo.get_by_pair(pair, limit=limit)
        return [
            {
                "id": l.id,
                "pair": l.pair,
                "mode": l.mode,
                "verdict": l.verdict,
                "confidence": l.confidence,
                "reasoning": l.reasoning,
                "market_summary": l.market_summary,
                "risk_warnings": l.risk_warnings,
                "signal_direction": l.signal_direction,
                "model_used": l.model_used,
                "latency_ms": l.latency_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]


# ── Post-trade reviews ────────────────────────────────

@router.get("/post-trade-reviews")
async def get_post_trade_reviews(limit: int = 30, user_id: int = Depends(get_user_id)):
    """Get recent post-trade AI reviews."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session, user_id=user_id)
        logs = await repo.get_by_mode("post_trade", limit=limit)
        return [
            {
                "id": l.id,
                "pair": l.pair,
                "mode": l.mode,
                "verdict": l.verdict,
                "confidence": l.confidence,
                "reasoning": l.reasoning,
                "signal_direction": l.signal_direction,
                "signal_strategy": l.signal_strategy,
                "score": (l.suggested_adjustments or {}).get("score"),
                "lessons_learned": (l.suggested_adjustments or {}).get("lessons_learned", []),
                "what_went_well": (l.suggested_adjustments or {}).get("what_went_well", []),
                "what_could_improve": (l.suggested_adjustments or {}).get("what_could_improve", []),
                "model_used": l.model_used,
                "latency_ms": l.latency_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]


# ── Stats ──────────────────────────────────────────────

@router.get("/stats")
async def get_stats(user_id: int = Depends(get_user_id)):
    """Get AI analysis statistics."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session, user_id=user_id)
        return await repo.get_stats()


# ── Manual analysis trigger ────────────────────────────

class ManualAnalysisRequest(BaseModel):
    pair: str
    mode: str = "market_review"


@router.post("/analyze")
async def trigger_analysis(body: ManualAnalysisRequest, user_id: int = Depends(get_user_id)):
    """Trigger a manual AI analysis for a pair."""
    from bot.crypto import decrypt
    from bot.db.repository import SettingsRepository
    from bot.db.session import get_session as _get_session

    # Read fresh AI settings from DB for this user
    ai_enabled = settings.ai_enabled
    ai_api_key = settings.ai_api_key
    try:
        async with _get_session() as session:
            repo = SettingsRepository(session, user_id=user_id)
            db_values = await repo.get_decrypted_values(decrypt)
            if db_values:
                if "ai_enabled" in db_values:
                    ai_enabled = str(db_values["ai_enabled"]).lower() in ("true", "1", "yes", "on")
                if "ai_api_key" in db_values:
                    ai_api_key = db_values["ai_api_key"]
                # Apply all AI settings to in-memory so ClaudeAnalyzer picks them up
                settings.apply_db_overrides(db_values)
    except Exception:
        pass

    if not ai_enabled or not ai_api_key:
        return {"error": "AI non configure. Activez-le dans les parametres."}

    analyzer = ClaudeAnalyzer()

    try:
        # Fetch some market data for context
        from bot.broker.kraken_rest import KrakenRestClient

        broker = KrakenRestClient()
        await broker.connect()

        try:
            from bot.data.historical import HistoricalDataManager
            from bot.data.indicators import add_all_indicators

            data_mgr = HistoricalDataManager(broker)
            df = await data_mgr.get_bars(body.pair, interval_minutes=60, count=100)

            indicators = {}
            recent_bars = []
            if not df.empty:
                df = add_all_indicators(df)
                last = df.iloc[-1]
                for col in ["rsi", "macd", "macd_histogram", "atr", "adx", "ema_20", "ema_50", "ema_200"]:
                    if col in df.columns and not last.get(col) is None:
                        try:
                            indicators[col] = float(last[col])
                        except (TypeError, ValueError):
                            pass

                for _, row in df.tail(10).iterrows():
                    recent_bars.append({
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    })

            mode = AnalysisMode(body.mode)
            request = AIAnalysisRequest(
                mode=mode,
                pair=body.pair,
                indicators=indicators,
                recent_bars=recent_bars,
            )

            result = await analyzer.analyze(request)

            # Save to DB scoped to user
            async with get_session() as session:
                ai_repo = AIAnalysisRepository(session, user_id=user_id)
                await ai_repo.save(
                    pair=body.pair,
                    mode=body.mode,
                    verdict=result.verdict.value,
                    confidence=result.confidence,
                    reasoning=result.reasoning,
                    market_summary=result.market_summary,
                    risk_warnings=result.risk_warnings,
                    suggested_adjustments=result.suggested_adjustments,
                    model_used=result.model_used,
                    latency_ms=result.latency_ms,
                )

            return {
                "verdict": result.verdict.value,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "market_summary": result.market_summary,
                "risk_warnings": result.risk_warnings,
                "suggested_adjustments": result.suggested_adjustments,
                "model": result.model_used,
                "latency_ms": result.latency_ms,
            }
        finally:
            await broker.disconnect()
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        await analyzer.close()
