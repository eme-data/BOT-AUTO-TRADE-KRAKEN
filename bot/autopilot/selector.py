"""Strategy selection based on market regime and score."""

from __future__ import annotations

import structlog

from bot.autopilot.models import MarketScore

logger = structlog.get_logger(__name__)


def select_strategy(
    score: MarketScore,
    allowed_strategies: list[str] | None = None,
) -> str | None:
    """Pick the best strategy for the given market regime.

    Parameters
    ----------
    score:
        Market score for the pair.
    allowed_strategies:
        Optional whitelist of strategy keys. If set, the selector will only
        return a strategy present in this list — the regime-based preference
        is used when it matches, otherwise the first whitelisted strategy is
        chosen. Returns ``None`` if the whitelist is non-empty and no entry
        applies. Pass ``None`` (or omit) to restore unrestricted selection.
    """
    # Regime-based preference (legacy logic)
    if score.regime == "trending":
        preferred = "macd_trend"
    elif score.regime == "ranging":
        preferred = "rsi_mean_reversion"
    elif score.regime == "volatile":
        preferred = "macd_trend" if score.momentum_score > 0.6 else "rsi_mean_reversion"
    else:
        preferred = "rsi_mean_reversion"

    if allowed_strategies is None or not allowed_strategies:
        strategy: str | None = preferred
    elif preferred in allowed_strategies:
        strategy = preferred
    else:
        # Fallback to the first whitelisted strategy — works for regime-agnostic
        # strategies like funding_divergence that trigger on external signals.
        strategy = allowed_strategies[0] if allowed_strategies else None

    if strategy is None:
        logger.info(
            "autopilot_no_allowed_strategy",
            pair=score.pair, regime=score.regime,
        )
        return None

    score.recommended_strategy = strategy
    logger.debug(
        "strategy_selected",
        pair=score.pair,
        regime=score.regime,
        strategy=strategy,
        whitelisted=bool(allowed_strategies),
    )
    return strategy


def position_size_factor(score: MarketScore, min_score: float = 0.55) -> float:
    """Scale position size by score: 0.5 at threshold → 1.0 at 0.80+."""
    if score.composite < min_score:
        return 0.0
    return min(0.5 + (score.composite - min_score) / (0.80 - min_score) * 0.5, 1.0)
