"""Multi-timeframe scoring of market quality."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import structlog

from bot.autopilot.models import MarketScore
from bot.data.historical import HistoricalDataManager
from bot.data.indicators import add_all_indicators, detect_regime, ema_alignment

logger = structlog.get_logger(__name__)

# Score weights (without Polymarket)
W_TREND = 0.35
W_MOMENTUM = 0.25
W_VOLATILITY = 0.15
W_ALIGNMENT = 0.25

# Score weights (with Polymarket sentiment)
W_TREND_PM = 0.25
W_MOMENTUM_PM = 0.20
W_VOLATILITY_PM = 0.10
W_ALIGNMENT_PM = 0.20
W_SENTIMENT_PM = 0.25


class MarketScorer:
    """Scores market quality using multi-timeframe analysis."""

    def __init__(self, data_mgr: HistoricalDataManager, polymarket_client=None) -> None:
        self._data = data_mgr
        self._polymarket = polymarket_client
        self._cache: dict[str, MarketScore] = {}
        self._cache_ttl = 1800  # 30 minutes

    async def score(self, pair: str) -> MarketScore:
        """Score a single pair. Uses cache if fresh enough."""
        cached = self._cache.get(pair)
        if cached:
            age = (datetime.now(timezone.utc) - cached.scored_at).total_seconds()
            if age < self._cache_ttl:
                return cached

        # Fetch H1 and D1 bars
        df_h1 = await self._data.get_bars(pair, interval_minutes=60, count=100)
        df_d1 = await self._data.get_bars(pair, interval_minutes=1440, count=50)

        if df_h1.empty:
            logger.warning("scorer_no_data", pair=pair, tf="H1")
            return MarketScore(pair=pair)

        # Add indicators
        df_h1 = add_all_indicators(df_h1)
        if not df_d1.empty:
            df_d1 = add_all_indicators(df_d1)

        # Calculate sub-scores
        trend = self._trend_score(df_h1, df_d1)
        momentum = self._momentum_score(df_h1)
        volatility = self._volatility_score(df_h1)
        alignment = self._alignment_score(df_h1, df_d1)
        sentiment = await self._sentiment_score(pair)

        if self._polymarket and sentiment != 0.5:
            composite = (
                W_TREND_PM * trend
                + W_MOMENTUM_PM * momentum
                + W_VOLATILITY_PM * volatility
                + W_ALIGNMENT_PM * alignment
                + W_SENTIMENT_PM * sentiment
            )
        else:
            composite = (
                W_TREND * trend
                + W_MOMENTUM * momentum
                + W_VOLATILITY * volatility
                + W_ALIGNMENT * alignment
            )

        regime = detect_regime(df_h1)
        direction = ema_alignment(df_h1)

        result = MarketScore(
            pair=pair,
            trend_score=trend,
            momentum_score=momentum,
            volatility_score=volatility,
            alignment_score=alignment,
            sentiment_score=sentiment,
            composite=composite,
            regime=regime,
            direction_bias=direction,
        )

        self._cache[pair] = result
        logger.debug(
            "market_scored",
            pair=pair,
            composite=round(composite, 3),
            regime=regime,
            bias=direction,
        )
        return result

    def _trend_score(self, h1: pd.DataFrame, d1: pd.DataFrame) -> float:
        score = 0.0
        if "adx" in h1.columns:
            adx = h1["adx"].iloc[-1]
            if not pd.isna(adx):
                score += min(adx / 50, 1.0) * 0.6

        if not d1.empty and "adx" in d1.columns:
            adx_d = d1["adx"].iloc[-1]
            if not pd.isna(adx_d):
                score += min(adx_d / 50, 1.0) * 0.4

        return min(score, 1.0)

    def _momentum_score(self, df: pd.DataFrame) -> float:
        score = 0.0
        if "rsi" in df.columns:
            rsi = df["rsi"].iloc[-1]
            if not pd.isna(rsi):
                # Score peaks near extremes (strong momentum)
                distance = abs(rsi - 50) / 50
                score += distance * 0.5

        if "macd_histogram" in df.columns:
            hist = df["macd_histogram"].iloc[-1]
            hist_prev = df["macd_histogram"].iloc[-2] if len(df) > 1 else hist
            if not pd.isna(hist) and not pd.isna(hist_prev):
                # Accelerating histogram = strong momentum
                if abs(hist) > abs(hist_prev):
                    score += 0.5

        return min(score, 1.0)

    def _volatility_score(self, df: pd.DataFrame) -> float:
        if "atr" not in df.columns or "close" not in df.columns:
            return 0.5
        atr = df["atr"].iloc[-1]
        close = df["close"].iloc[-1]
        if pd.isna(atr) or close == 0:
            return 0.5

        atr_pct = (atr / close) * 100
        # Optimal volatility: 0.5% – 3% for crypto
        if 0.5 <= atr_pct <= 3.0:
            return 1.0
        elif atr_pct < 0.5:
            return atr_pct / 0.5
        else:
            return max(1.0 - (atr_pct - 3.0) / 5.0, 0.0)

    def _alignment_score(self, h1: pd.DataFrame, d1: pd.DataFrame) -> float:
        h1_align = ema_alignment(h1)
        d1_align = ema_alignment(d1) if not d1.empty else "neutral"

        if h1_align == d1_align and h1_align != "neutral":
            return 1.0
        elif h1_align != "neutral" and d1_align == "neutral":
            return 0.6
        elif h1_align == "neutral":
            return 0.3
        else:
            return 0.1  # conflicting timeframes

    async def _sentiment_score(self, pair: str) -> float:
        """Get Polymarket sentiment score for a pair (0-1, 0.5=neutral)."""
        if not self._polymarket:
            return 0.5
        try:
            sentiment = await self._polymarket.get_sentiment_for_pair(pair)
            if sentiment is None:
                return 0.5
            # bullish_probability is already 0-1, use it directly
            # Weight by confidence (based on market count/volume)
            raw = sentiment.bullish_probability
            confidence = sentiment.confidence
            # Blend towards neutral (0.5) when confidence is low
            return 0.5 + (raw - 0.5) * confidence
        except Exception as exc:
            logger.warning("polymarket_score_error", pair=pair, error=str(exc))
            return 0.5
