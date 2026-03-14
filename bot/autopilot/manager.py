"""Autopilot manager – orchestrates scan → score → activate cycle."""

from __future__ import annotations

import structlog

from bot.autopilot.models import MarketScore
from bot.autopilot.scanner import MarketScanner
from bot.autopilot.scorer import MarketScorer
from bot.autopilot.selector import select_strategy, position_size_factor
from bot.broker.kraken_rest import KrakenRestClient
from bot.broker.kraken_ws import KrakenWSClient
from bot.config import settings
from bot.data.historical import HistoricalDataManager
from bot.strategies.registry import StrategyRegistry

logger = structlog.get_logger(__name__)


class AutopilotManager:
    """Discovers, scores, and activates the best crypto pairs."""

    def __init__(
        self,
        broker: KrakenRestClient,
        ws_client: KrakenWSClient,
        data_mgr: HistoricalDataManager,
        strategy_registry: StrategyRegistry,
    ) -> None:
        self._broker = broker
        self._ws = ws_client
        self._scanner = MarketScanner(broker)
        self._scorer = MarketScorer(data_mgr)
        self._registry = strategy_registry
        self._active_pairs: dict[str, MarketScore] = {}
        self.enabled = settings.autopilot_enabled
        self.shadow_mode = settings.autopilot_shadow_mode
        self.max_active = settings.autopilot_max_active
        self.min_score = settings.autopilot_min_score

    async def run_scan_cycle(self) -> list[MarketScore]:
        """Full autopilot cycle: scan → score → activate top N."""
        if not self.enabled:
            return []

        logger.info("autopilot_cycle_start")

        # 1. Discover candidates
        candidates = await self._scanner.scan_discovery()

        # 2. Score each candidate
        scores: list[MarketScore] = []
        for candidate in candidates:
            try:
                score = await self._scorer.score(candidate.pair)
                if score.composite >= self.min_score:
                    scores.append(score)
            except Exception as exc:
                logger.warning(
                    "scorer_error", pair=candidate.pair, error=str(exc)
                )

        # 3. Rank and keep top N
        scores.sort(key=lambda s: s.composite, reverse=True)
        top = scores[: self.max_active]

        # 4. Deactivate pairs no longer in top
        current_pairs = set(self._active_pairs.keys())
        new_pairs = {s.pair for s in top}
        to_remove = current_pairs - new_pairs

        for pair in to_remove:
            await self._deactivate(pair)

        # 5. Activate new pairs
        for score in top:
            if score.pair not in self._active_pairs:
                await self._activate(score)
            else:
                self._active_pairs[score.pair] = score

        logger.info(
            "autopilot_cycle_done",
            active=len(self._active_pairs),
            scores=[
                {"pair": s.pair, "score": round(s.composite, 3)} for s in top
            ],
        )
        return top

    async def _activate(self, score: MarketScore) -> None:
        strategy_name = select_strategy(score)
        key = f"ap_{strategy_name}_{score.pair.replace('/', '_')}"

        try:
            strategy = self._registry.create_strategy(strategy_name)
            self._registry.register(key, strategy)
            await self._ws.subscribe_ticker([score.pair])
            self._active_pairs[score.pair] = score
            logger.info(
                "autopilot_activated",
                pair=score.pair,
                strategy=strategy_name,
                score=round(score.composite, 3),
            )
        except Exception as exc:
            logger.error(
                "autopilot_activate_error",
                pair=score.pair,
                error=str(exc),
            )

    async def _deactivate(self, pair: str) -> None:
        score = self._active_pairs.pop(pair, None)
        if not score:
            return

        key_prefix = f"ap_"
        keys_to_remove = [
            k for k in self._registry.strategies if k.startswith(key_prefix) and pair.replace("/", "_") in k
        ]
        for key in keys_to_remove:
            self._registry.unregister(key)

        await self._ws.unsubscribe_ticker([pair])
        logger.info("autopilot_deactivated", pair=pair)

    @property
    def active_scores(self) -> dict[str, MarketScore]:
        return dict(self._active_pairs)
