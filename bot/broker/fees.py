"""Kraken fee calculator based on volume-based tier structure."""

from __future__ import annotations


class KrakenFeeCalculator:
    """Kraken fee structure (volume-based tiers).

    Fees are looked up by 30-day trailing volume in USD.
    Each tier defines a maker and taker fee as a decimal fraction.
    """

    # Default Kraken fee tiers: (min_volume_usd, maker_fee, taker_fee)
    TIERS: list[tuple[float, float, float]] = [
        (0, 0.0025, 0.0040),  # $0-$50K: 0.25% maker, 0.40% taker
        (50_000, 0.0020, 0.0035),  # $50K-$100K
        (100_000, 0.0014, 0.0024),  # $100K-$250K
        (250_000, 0.0012, 0.0022),  # $250K-$500K
        (500_000, 0.0010, 0.0020),  # $500K-$1M
        (1_000_000, 0.0008, 0.0018),  # $1M-$2.5M
        (2_500_000, 0.0006, 0.0016),  # $2.5M-$5M
        (5_000_000, 0.0004, 0.0014),  # $5M-$10M
        (10_000_000, 0.0002, 0.0012),  # $10M+
    ]

    def __init__(self, thirty_day_volume: float = 0.0) -> None:
        self.thirty_day_volume = thirty_day_volume
        self._maker_fee, self._taker_fee = self._get_tier_fees()

    def _get_tier_fees(self) -> tuple[float, float]:
        """Return (maker_fee, taker_fee) for the current 30-day volume."""
        maker = self.TIERS[0][1]
        taker = self.TIERS[0][2]
        for min_volume, tier_maker, tier_taker in self.TIERS:
            if self.thirty_day_volume >= min_volume:
                maker = tier_maker
                taker = tier_taker
            else:
                break
        return maker, taker

    @property
    def maker_fee(self) -> float:
        """Current maker fee as a decimal fraction."""
        return self._maker_fee

    @property
    def taker_fee(self) -> float:
        """Current taker fee as a decimal fraction."""
        return self._taker_fee

    def estimate_fee(
        self, size: float, price: float, is_maker: bool = False
    ) -> float:
        """Estimate the fee in quote currency for a single trade.

        Args:
            size: Order size in base currency.
            price: Price per unit in quote currency.
            is_maker: True for maker (limit) orders, False for taker (market).

        Returns:
            Estimated fee in quote currency.
        """
        notional = size * price
        rate = self._maker_fee if is_maker else self._taker_fee
        return notional * rate

    def estimate_round_trip(
        self,
        size: float,
        entry_price: float,
        exit_price: float,
        is_maker: bool = False,
    ) -> float:
        """Estimate total fees for opening and closing a position.

        Args:
            size: Order size in base currency.
            entry_price: Entry price per unit.
            exit_price: Exit price per unit.
            is_maker: True if both legs are maker orders.

        Returns:
            Total estimated fees in quote currency for the round trip.
        """
        entry_fee = self.estimate_fee(size, entry_price, is_maker=is_maker)
        exit_fee = self.estimate_fee(size, exit_price, is_maker=is_maker)
        return entry_fee + exit_fee
