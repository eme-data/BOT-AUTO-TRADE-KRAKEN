"""Strategy selection based on market regime and score."""

from __future__ import annotations

import structlog

from bot.autopilot.models import MarketScore

logger = structlog.get_logger(__name__)


def select_strategy(score: MarketScore) -> str:
    """Pick the best strategy for the given market regime.

    Returns strategy name (key in STRATEGY_CLASSES).
    """
    if score.regime == "trending":
        strategy = "macd_trend"
    elif score.regime == "ranging":
        strategy = "rsi_mean_reversion"
    elif score.regime == "volatile":
        # High momentum → trend-follow; fading → mean-revert
        if score.momentum_score > 0.6:
            strategy = "macd_trend"
        else:
            strategy = "rsi_mean_reversion"
    else:
        strategy = "rsi_mean_reversion"

    score.recommended_strategy = strategy
    logger.debug(
        "strategy_selected",
        pair=score.pair,
        regime=score.regime,
        strategy=strategy,
    )
    return strategy


def position_size_factor(score: MarketScore, min_score: float = 0.55) -> float:
    """Scale position size by score: 0.5 at threshold → 1.0 at 0.80+."""
    if score.composite < min_score:
        return 0.0
    return min(0.5 + (score.composite - min_score) / (0.80 - min_score) * 0.5, 1.0)
