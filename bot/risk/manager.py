"""Risk manager – validates signals before execution."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from bot.broker.models import AccountBalance, Direction, Position
from bot.config import settings
from bot.strategies.base import Signal, SignalType

logger = structlog.get_logger(__name__)

# ── Correlation groups for crypto ──────────────────────
CORRELATION_GROUPS: dict[str, list[str]] = {
    "btc_ecosystem": ["BTC/USD", "BTC/EUR", "BTC/USDT"],
    "eth_ecosystem": ["ETH/USD", "ETH/EUR", "ETH/USDT", "ETH/BTC"],
    "stablecoins": ["USDT/USD", "USDC/USD", "DAI/USD"],
    "defi": ["UNI/USD", "AAVE/USD", "LINK/USD", "MKR/USD"],
    "layer1": ["SOL/USD", "ADA/USD", "AVAX/USD", "DOT/USD"],
    "meme": ["DOGE/USD", "SHIB/USD"],
}


@dataclass
class RiskCheckResult:
    allowed: bool
    reason: str = ""


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    trades_today: int = 0
    emergency_stop: bool = False


class RiskManager:
    """Validates trade signals against risk rules."""

    def __init__(self) -> None:
        self.state = RiskState()
        self.max_daily_loss = settings.bot_max_daily_loss
        self.max_position_size = settings.bot_max_position_size
        self.max_open_positions = settings.bot_max_open_positions
        self.max_per_pair = settings.bot_max_per_pair
        self.risk_per_trade_pct = settings.bot_risk_per_trade_pct

    def check_signal(
        self,
        signal: Signal,
        open_positions: list[Position],
        balance: AccountBalance,
    ) -> RiskCheckResult:
        """Run all risk checks. Returns allowed=True if signal is OK."""

        # Emergency stop
        if self.state.emergency_stop:
            return RiskCheckResult(False, "Emergency stop active")

        # Daily loss limit
        if self.state.daily_pnl <= self.max_daily_loss:
            self.state.emergency_stop = True
            logger.critical(
                "emergency_stop",
                daily_pnl=self.state.daily_pnl,
                limit=self.max_daily_loss,
            )
            return RiskCheckResult(
                False, f"Daily loss limit reached: {self.state.daily_pnl:.2f}"
            )

        # Max open positions
        if len(open_positions) >= self.max_open_positions:
            return RiskCheckResult(
                False,
                f"Max open positions ({self.max_open_positions}) reached",
            )

        # Max positions per pair
        pair_positions = [p for p in open_positions if p.pair == signal.pair]
        if len(pair_positions) >= self.max_per_pair:
            return RiskCheckResult(
                False, f"Max per pair ({self.max_per_pair}) reached for {signal.pair}"
            )

        # No hedging – block opposite direction on same pair
        for pos in pair_positions:
            if pos.direction != signal.direction:
                return RiskCheckResult(
                    False,
                    f"Opposite position already open on {signal.pair}",
                )

        # Correlation check
        corr = self._check_correlation(signal, open_positions)
        if not corr.allowed:
            return corr

        return RiskCheckResult(True)

    def calculate_position_size(
        self,
        signal: Signal,
        balance: AccountBalance,
        current_price: float,
    ) -> float:
        """Calculate position size based on risk percentage."""
        if signal.size:
            return min(signal.size, self.max_position_size)

        if not signal.stop_loss_pct or signal.stop_loss_pct == 0:
            # Fallback: use default stop %
            stop_pct = settings.bot_default_stop_pct
        else:
            stop_pct = signal.stop_loss_pct

        # Risk amount = balance × risk%
        risk_amount = balance.available_balance * (self.risk_per_trade_pct / 100)

        # Size = risk_amount / (price × stop%)
        if current_price > 0 and stop_pct > 0:
            size = risk_amount / (current_price * (stop_pct / 100))
        else:
            size = 0.0

        return min(size, self.max_position_size)

    def update_daily_pnl(self, pnl: float) -> None:
        self.state.daily_pnl += pnl
        logger.debug("daily_pnl_updated", daily_pnl=self.state.daily_pnl)

    def reset_daily(self) -> None:
        self.state.daily_pnl = 0.0
        self.state.trades_today = 0
        self.state.emergency_stop = False
        logger.info("risk_daily_reset")

    def _check_correlation(
        self, signal: Signal, positions: list[Position]
    ) -> RiskCheckResult:
        signal_group = self._find_group(signal.pair)
        if not signal_group:
            return RiskCheckResult(True)

        for pos in positions:
            pos_group = self._find_group(pos.pair)
            if pos_group == signal_group and pos.direction == signal.direction:
                return RiskCheckResult(
                    False,
                    f"Correlated position: {pos.pair} ({signal_group}) "
                    f"already {pos.direction.value}",
                )
        return RiskCheckResult(True)

    @staticmethod
    def _find_group(pair: str) -> str | None:
        for group_name, pairs in CORRELATION_GROUPS.items():
            if pair in pairs:
                return group_name
        return None
