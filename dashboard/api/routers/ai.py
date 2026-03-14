"""AI Analysis endpoints – view logs, trigger reviews, check status."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bot.ai.analyzer import ClaudeAnalyzer
from bot.ai.models import AnalysisMode, AIAnalysisRequest
from bot.config import settings
from bot.db.repository import AIAnalysisRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user

router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(get_current_user)],
)


# ── Status ─────────────────────────────────────────────

@router.get("/status")
async def ai_status():
    """Check if AI is configured and enabled."""
    return {
        "enabled": settings.ai_enabled,
        "configured": bool(settings.ai_api_key),
        "model": settings.ai_model,
        "modes": {
            "pre_trade": settings.ai_pre_trade_enabled,
            "market_review": settings.ai_market_review_enabled,
            "sentiment": settings.ai_sentiment_enabled,
            "post_trade": settings.ai_post_trade_enabled,
        },
    }


# ── Analysis logs ──────────────────────────────────────

@router.get("/logs")
async def get_logs(limit: int = 50):
    """Get recent AI analysis logs."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session)
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
async def get_logs_by_pair(pair: str, limit: int = 20):
    """Get AI analysis logs for a specific pair."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session)
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


# ── Stats ──────────────────────────────────────────────

@router.get("/stats")
async def get_stats():
    """Get AI analysis statistics."""
    async with get_session() as session:
        repo = AIAnalysisRepository(session)
        return await repo.get_stats()


# ── Manual analysis trigger ────────────────────────────

class ManualAnalysisRequest(BaseModel):
    pair: str
    mode: str = "market_review"


@router.post("/analyze")
async def trigger_analysis(body: ManualAnalysisRequest):
    """Trigger a manual AI analysis for a pair."""
    if not settings.ai_enabled or not settings.ai_api_key:
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

            # Save to DB
            async with get_session() as session:
                ai_repo = AIAnalysisRepository(session)
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
