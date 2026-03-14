"""Data access layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    AdminUser,
    AIAnalysisLog,
    AppSetting,
    DailyPnL,
    SignalLog,
    StrategyState,
    Trade,
    WatchedMarket,
)


class TradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_trade(self, **kwargs: Any) -> Trade:
        trade = Trade(**kwargs)
        self.session.add(trade)
        await self.session.flush()
        return trade

    async def close_trade(
        self, order_id: str, exit_price: float, profit: float, fee: float = 0.0
    ) -> None:
        await self.session.execute(
            update(Trade)
            .where(Trade.order_id == order_id)
            .values(
                exit_price=exit_price,
                profit=profit,
                fee=Trade.fee + fee,
                status="CLOSED",
                closed_at=datetime.now(timezone.utc),
            )
        )

    async def get_open_trades(self) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).where(Trade.status == "OPEN").order_by(Trade.opened_at)
        )
        return list(result.scalars().all())

    async def get_recent_trades(self, limit: int = 50) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_daily_pnl(self, date: datetime) -> float:
        result = await self.session.execute(
            select(Trade.profit)
            .where(Trade.status == "CLOSED")
            .where(Trade.closed_at >= date)
        )
        profits = result.scalars().all()
        return sum(p for p in profits if p is not None)


class SignalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_signal(self, **kwargs: Any) -> SignalLog:
        sig = SignalLog(**kwargs)
        self.session.add(sig)
        await self.session.flush()
        return sig


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        result = await self.session.execute(
            select(AppSetting.value).where(AppSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def get_with_meta(self, key: str) -> AppSetting | None:
        result = await self.session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str, encrypted: bool = False) -> None:
        existing = await self.session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        row = existing.scalar_one_or_none()
        if row:
            row.value = value
            row.encrypted = encrypted
        else:
            self.session.add(
                AppSetting(key=key, value=value, encrypted=encrypted)
            )

    async def get_all(self) -> dict[str, str]:
        result = await self.session.execute(select(AppSetting))
        return {
            row.key: row.value for row in result.scalars().all() if row.value
        }

    async def get_all_with_meta(self) -> list[AppSetting]:
        result = await self.session.execute(select(AppSetting))
        return list(result.scalars().all())

    async def get_decrypted_values(self, decrypt_fn) -> dict[str, str]:
        """Load all settings, decrypting encrypted ones."""
        rows = await self.get_all_with_meta()
        out: dict[str, str] = {}
        for row in rows:
            if not row.value:
                continue
            if row.encrypted:
                try:
                    out[row.key] = decrypt_fn(row.value)
                except Exception:
                    out[row.key] = ""  # corrupted – skip
            else:
                out[row.key] = row.value
        return out

    async def bulk_set(
        self, values: dict[str, str], sensitive_keys: set[str], encrypt_fn
    ) -> int:
        """Save multiple settings at once, encrypting sensitive ones."""
        count = 0
        for key, value in values.items():
            is_sensitive = key in sensitive_keys
            stored = encrypt_fn(value) if is_sensitive and value else value
            await self.set(key, stored, encrypted=is_sensitive)
            count += 1
        return count


class StrategyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_enabled(self) -> list[StrategyState]:
        result = await self.session.execute(
            select(StrategyState).where(StrategyState.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def save_state(
        self, name: str, enabled: bool, config: dict | None, state: dict | None
    ) -> None:
        existing = await self.session.execute(
            select(StrategyState).where(StrategyState.name == name)
        )
        row = existing.scalar_one_or_none()
        if row:
            row.enabled = enabled
            row.config = config
            row.state = state
        else:
            self.session.add(
                StrategyState(name=name, enabled=enabled, config=config, state=state)
            )


class WatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self) -> list[WatchedMarket]:
        result = await self.session.execute(
            select(WatchedMarket).where(WatchedMarket.active.is_(True))
        )
        return list(result.scalars().all())

    async def add(self, pair: str) -> None:
        self.session.add(WatchedMarket(pair=pair))

    async def remove(self, pair: str) -> None:
        await self.session.execute(
            delete(WatchedMarket).where(WatchedMarket.pair == pair)
        )


class AIAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, **kwargs: Any) -> AIAnalysisLog:
        log = AIAnalysisLog(**kwargs)
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_recent(self, limit: int = 50) -> list[AIAnalysisLog]:
        result = await self.session.execute(
            select(AIAnalysisLog)
            .order_by(AIAnalysisLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_pair(self, pair: str, limit: int = 20) -> list[AIAnalysisLog]:
        result = await self.session.execute(
            select(AIAnalysisLog)
            .where(AIAnalysisLog.pair == pair)
            .order_by(AIAnalysisLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_stats(self) -> dict[str, Any]:
        all_logs = await self.get_recent(limit=500)
        if not all_logs:
            return {"total": 0}
        approvals = sum(1 for l in all_logs if l.verdict == "APPROVE")
        rejections = sum(1 for l in all_logs if l.verdict == "REJECT")
        adjustments = sum(1 for l in all_logs if l.verdict == "ADJUST")
        avg_latency = sum(l.latency_ms for l in all_logs) / len(all_logs)
        avg_confidence = sum(l.confidence for l in all_logs) / len(all_logs)
        return {
            "total": len(all_logs),
            "approvals": approvals,
            "rejections": rejections,
            "adjustments": adjustments,
            "avg_latency_ms": round(avg_latency),
            "avg_confidence": round(avg_confidence, 3),
        }
