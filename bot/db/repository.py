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
    AuditLog,
    CopyTradingLink,
    DailyPnL,
    DCASchedule,
    ManualOrder,
    MarketJournalEntry,
    PortfolioTarget,
    PriceAlert,
    PushSubscription,
    SignalLog,
    StrategyState,
    Trade,
    TradeNote,
    WatchedMarket,
)


class TradeRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _user_filter(self, stmt):
        if self.user_id is not None:
            return stmt.where(Trade.user_id == self.user_id)
        return stmt

    async def create_trade(self, **kwargs: Any) -> Trade:
        if self.user_id is not None:
            kwargs.setdefault("user_id", self.user_id)
        trade = Trade(**kwargs)
        self.session.add(trade)
        await self.session.flush()
        return trade

    async def close_trade(
        self, order_id: str, exit_price: float, profit: float, fee: float = 0.0
    ) -> None:
        stmt = (
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
        if self.user_id is not None:
            stmt = stmt.where(Trade.user_id == self.user_id)
        await self.session.execute(stmt)

    async def get_open_trades(self) -> list[Trade]:
        stmt = select(Trade).where(Trade.status == "OPEN").order_by(Trade.opened_at)
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def get_recent_trades(self, limit: int = 50) -> list[Trade]:
        stmt = select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def get_trades_since(self, since: datetime) -> list[Trade]:
        stmt = (
            select(Trade)
            .where(Trade.opened_at >= since)
            .order_by(Trade.opened_at.desc())
        )
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def get_daily_pnl(self, date: datetime) -> float:
        stmt = (
            select(Trade.profit)
            .where(Trade.status == "CLOSED")
            .where(Trade.closed_at >= date)
        )
        result = await self.session.execute(self._user_filter(stmt))
        profits = result.scalars().all()
        return sum(p for p in profits if p is not None)


class TradeNoteRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def create(
        self,
        content: str,
        trade_id: int | None = None,
        tags: list[str] | None = None,
        mood: str | None = None,
    ) -> TradeNote:
        note = TradeNote(
            user_id=self.user_id,
            trade_id=trade_id,
            content=content,
            tags=tags,
            mood=mood,
        )
        self.session.add(note)
        await self.session.flush()
        return note

    async def get_by_trade(self, trade_id: int) -> list[TradeNote]:
        stmt = (
            select(TradeNote)
            .where(TradeNote.trade_id == trade_id)
            .where(TradeNote.user_id == self.user_id)
            .order_by(TradeNote.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, limit: int = 50) -> list[TradeNote]:
        stmt = (
            select(TradeNote)
            .where(TradeNote.user_id == self.user_id)
            .order_by(TradeNote.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        note_id: int,
        content: str | None = None,
        tags: list[str] | None = None,
        mood: str | None = None,
    ) -> TradeNote | None:
        stmt = (
            select(TradeNote)
            .where(TradeNote.id == note_id)
            .where(TradeNote.user_id == self.user_id)
        )
        result = await self.session.execute(stmt)
        note = result.scalar_one_or_none()
        if note is None:
            return None
        if content is not None:
            note.content = content
        if tags is not None:
            note.tags = tags
        if mood is not None:
            note.mood = mood
        return note

    async def delete(self, note_id: int) -> bool:
        stmt = (
            delete(TradeNote)
            .where(TradeNote.id == note_id)
            .where(TradeNote.user_id == self.user_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0


class SignalRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    async def log_signal(self, **kwargs: Any) -> SignalLog:
        if self.user_id is not None:
            kwargs.setdefault("user_id", self.user_id)
        sig = SignalLog(**kwargs)
        self.session.add(sig)
        await self.session.flush()
        return sig


class SettingsRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _base_filter(self, stmt):
        if self.user_id is not None:
            return stmt.where(AppSetting.user_id == self.user_id)
        return stmt.where(AppSetting.user_id.is_(None))

    async def get(self, key: str) -> str | None:
        stmt = select(AppSetting.value).where(AppSetting.key == key)
        result = await self.session.execute(self._base_filter(stmt))
        return result.scalar_one_or_none()

    async def get_with_meta(self, key: str) -> AppSetting | None:
        stmt = select(AppSetting).where(AppSetting.key == key)
        result = await self.session.execute(self._base_filter(stmt))
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str, encrypted: bool = False) -> None:
        stmt = select(AppSetting).where(AppSetting.key == key)
        existing = await self.session.execute(self._base_filter(stmt))
        row = existing.scalar_one_or_none()
        if row:
            row.value = value
            row.encrypted = encrypted
        else:
            self.session.add(
                AppSetting(
                    key=key, value=value, encrypted=encrypted, user_id=self.user_id
                )
            )

    async def get_all(self) -> dict[str, str]:
        result = await self.session.execute(self._base_filter(select(AppSetting)))
        return {
            row.key: row.value for row in result.scalars().all() if row.value
        }

    async def get_all_with_meta(self) -> list[AppSetting]:
        result = await self.session.execute(self._base_filter(select(AppSetting)))
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
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _user_filter(self, stmt):
        if self.user_id is not None:
            return stmt.where(StrategyState.user_id == self.user_id)
        return stmt

    async def get_enabled(self) -> list[StrategyState]:
        stmt = select(StrategyState).where(StrategyState.enabled.is_(True))
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def save_state(
        self, name: str, enabled: bool, config: dict | None, state: dict | None
    ) -> None:
        stmt = select(StrategyState).where(StrategyState.name == name)
        existing = await self.session.execute(self._user_filter(stmt))
        row = existing.scalar_one_or_none()
        if row:
            row.enabled = enabled
            row.config = config
            row.state = state
        else:
            self.session.add(
                StrategyState(
                    name=name, enabled=enabled, config=config,
                    state=state, user_id=self.user_id,
                )
            )


class WatchlistRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _user_filter(self, stmt):
        if self.user_id is not None:
            return stmt.where(WatchedMarket.user_id == self.user_id)
        return stmt

    async def get_active(self) -> list[WatchedMarket]:
        stmt = select(WatchedMarket).where(WatchedMarket.active.is_(True))
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def add(self, pair: str) -> None:
        self.session.add(WatchedMarket(pair=pair, user_id=self.user_id))

    async def remove(self, pair: str) -> None:
        stmt = delete(WatchedMarket).where(WatchedMarket.pair == pair)
        if self.user_id is not None:
            stmt = stmt.where(WatchedMarket.user_id == self.user_id)
        await self.session.execute(stmt)


class AIAnalysisRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _user_filter(self, stmt):
        if self.user_id is not None:
            return stmt.where(AIAnalysisLog.user_id == self.user_id)
        return stmt

    async def save(self, **kwargs: Any) -> AIAnalysisLog:
        if self.user_id is not None:
            kwargs.setdefault("user_id", self.user_id)
        log = AIAnalysisLog(**kwargs)
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_recent(self, limit: int = 50) -> list[AIAnalysisLog]:
        stmt = (
            select(AIAnalysisLog)
            .order_by(AIAnalysisLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def get_by_pair(self, pair: str, limit: int = 20) -> list[AIAnalysisLog]:
        stmt = (
            select(AIAnalysisLog)
            .where(AIAnalysisLog.pair == pair)
            .order_by(AIAnalysisLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def get_by_mode(self, mode: str, limit: int = 30) -> list[AIAnalysisLog]:
        stmt = (
            select(AIAnalysisLog)
            .where(AIAnalysisLog.mode == mode)
            .order_by(AIAnalysisLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(self._user_filter(stmt))
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


class AuditLogRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _user_filter(self, stmt):
        if self.user_id is not None:
            return stmt.where(AuditLog.user_id == self.user_id)
        return stmt

    async def log(
        self,
        action: str,
        resource: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=self.user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_recent(self, limit: int = 100) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())

    async def get_by_action(self, action: str, limit: int = 100) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(self._user_filter(stmt))
        return list(result.scalars().all())


class PushSubscriptionRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    async def save(self, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
        stmt = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        result = await self.session.execute(stmt)
        sub = result.scalar_one_or_none()
        if sub:
            sub.p256dh = p256dh
            sub.auth = auth
            sub.user_id = self.user_id
        else:
            sub = PushSubscription(
                user_id=self.user_id, endpoint=endpoint,
                p256dh=p256dh, auth=auth,
            )
            self.session.add(sub)
        await self.session.flush()
        return sub

    async def get_by_user(self, user_id: int) -> list[PushSubscription]:
        stmt = select(PushSubscription).where(PushSubscription.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self) -> list[PushSubscription]:
        result = await self.session.execute(select(PushSubscription))
        return list(result.scalars().all())

    async def delete_by_endpoint(self, endpoint: str) -> bool:
        stmt = delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
        result = await self.session.execute(stmt)
        return result.rowcount > 0


class PriceAlertRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def create(self, pair: str, condition: str, target_price: float, note: str | None = None) -> PriceAlert:
        alert = PriceAlert(
            user_id=self.user_id, pair=pair, condition=condition,
            target_price=target_price, note=note,
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_active(self) -> list[PriceAlert]:
        stmt = (
            select(PriceAlert)
            .where(PriceAlert.user_id == self.user_id)
            .where(PriceAlert.active.is_(True))
            .where(PriceAlert.triggered.is_(False))
            .order_by(PriceAlert.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self) -> list[PriceAlert]:
        stmt = (
            select(PriceAlert)
            .where(PriceAlert.user_id == self.user_id)
            .order_by(PriceAlert.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active_global(self) -> list[PriceAlert]:
        """Get all active alerts across all users (for the checker loop)."""
        stmt = (
            select(PriceAlert)
            .where(PriceAlert.active.is_(True))
            .where(PriceAlert.triggered.is_(False))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def trigger(self, alert_id: int) -> None:
        stmt = (
            update(PriceAlert)
            .where(PriceAlert.id == alert_id)
            .values(triggered=True, triggered_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def delete(self, alert_id: int) -> bool:
        stmt = (
            delete(PriceAlert)
            .where(PriceAlert.id == alert_id)
            .where(PriceAlert.user_id == self.user_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def toggle(self, alert_id: int, active: bool) -> None:
        stmt = (
            update(PriceAlert)
            .where(PriceAlert.id == alert_id)
            .where(PriceAlert.user_id == self.user_id)
            .values(active=active)
        )
        await self.session.execute(stmt)


class DCAScheduleRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def create(self, pair: str, amount_usd: float, frequency: str, next_run: datetime) -> DCASchedule:
        sched = DCASchedule(
            user_id=self.user_id, pair=pair, amount_usd=amount_usd,
            frequency=frequency, next_run=next_run,
        )
        self.session.add(sched)
        await self.session.flush()
        return sched

    async def get_all(self) -> list[DCASchedule]:
        stmt = (
            select(DCASchedule)
            .where(DCASchedule.user_id == self.user_id)
            .order_by(DCASchedule.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_due_global(self, now: datetime) -> list[DCASchedule]:
        """Get all active DCA schedules that are due (across all users)."""
        stmt = (
            select(DCASchedule)
            .where(DCASchedule.active.is_(True))
            .where(DCASchedule.next_run <= now)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def record_execution(self, sched_id: int, amount_spent: float, amount_bought: float, next_run: datetime) -> None:
        stmt = select(DCASchedule).where(DCASchedule.id == sched_id)
        result = await self.session.execute(stmt)
        sched = result.scalar_one_or_none()
        if sched:
            sched.last_run = datetime.now(timezone.utc)
            sched.next_run = next_run
            sched.total_invested = (sched.total_invested or 0) + amount_spent
            sched.total_bought = (sched.total_bought or 0) + amount_bought
            sched.executions = (sched.executions or 0) + 1

    async def toggle(self, sched_id: int, active: bool) -> None:
        stmt = (
            update(DCASchedule)
            .where(DCASchedule.id == sched_id)
            .where(DCASchedule.user_id == self.user_id)
            .values(active=active)
        )
        await self.session.execute(stmt)

    async def delete(self, sched_id: int) -> bool:
        stmt = (
            delete(DCASchedule)
            .where(DCASchedule.id == sched_id)
            .where(DCASchedule.user_id == self.user_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0


class CopyTradingRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def create_link(self, leader_id: int, multiplier: float = 1.0, max_per_trade: float | None = None) -> CopyTradingLink:
        link = CopyTradingLink(
            follower_id=self.user_id, leader_id=leader_id,
            multiplier=multiplier, max_per_trade=max_per_trade,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def get_my_links(self) -> list[CopyTradingLink]:
        """Links where I am the follower."""
        stmt = (
            select(CopyTradingLink)
            .where(CopyTradingLink.follower_id == self.user_id)
            .order_by(CopyTradingLink.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_followers(self, leader_id: int) -> list[CopyTradingLink]:
        """Get all active followers of a leader."""
        stmt = (
            select(CopyTradingLink)
            .where(CopyTradingLink.leader_id == leader_id)
            .where(CopyTradingLink.active.is_(True))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_leaders_stats(self) -> list[dict]:
        """Get performance stats for all potential leaders."""
        stmt = select(AdminUser)
        result = await self.session.execute(stmt)
        users = list(result.scalars().all())

        stats = []
        for user in users:
            trade_stmt = (
                select(Trade)
                .where(Trade.user_id == user.id)
                .where(Trade.status == "CLOSED")
            )
            trade_result = await self.session.execute(trade_stmt)
            trades = list(trade_result.scalars().all())
            if not trades:
                continue
            total_pnl = sum(t.profit or 0 for t in trades)
            wins = sum(1 for t in trades if (t.profit or 0) > 0)
            stats.append({
                "user_id": user.id,
                "username": user.username,
                "total_trades": len(trades),
                "total_pnl": round(total_pnl, 2),
                "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
            })
        return sorted(stats, key=lambda s: s["total_pnl"], reverse=True)

    async def toggle(self, link_id: int, active: bool) -> None:
        stmt = (
            update(CopyTradingLink)
            .where(CopyTradingLink.id == link_id)
            .where(CopyTradingLink.follower_id == self.user_id)
            .values(active=active)
        )
        await self.session.execute(stmt)

    async def delete(self, link_id: int) -> bool:
        stmt = (
            delete(CopyTradingLink)
            .where(CopyTradingLink.id == link_id)
            .where(CopyTradingLink.follower_id == self.user_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0


class PortfolioTargetRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def get_all(self) -> list[PortfolioTarget]:
        stmt = (
            select(PortfolioTarget)
            .where(PortfolioTarget.user_id == self.user_id)
            .where(PortfolioTarget.active.is_(True))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_targets(self, targets: list[dict]) -> None:
        """Replace all targets with a new set. Each dict: {pair, target_pct}."""
        stmt = delete(PortfolioTarget).where(PortfolioTarget.user_id == self.user_id)
        await self.session.execute(stmt)
        for t in targets:
            self.session.add(PortfolioTarget(
                user_id=self.user_id, pair=t["pair"], target_pct=t["target_pct"],
            ))
        await self.session.flush()

    async def delete(self, target_id: int) -> bool:
        stmt = (
            delete(PortfolioTarget)
            .where(PortfolioTarget.id == target_id)
            .where(PortfolioTarget.user_id == self.user_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0


class MarketJournalRepository:
    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    async def save(self, **kwargs) -> MarketJournalEntry:
        if self.user_id is not None:
            kwargs.setdefault("user_id", self.user_id)
        entry = MarketJournalEntry(**kwargs)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_recent(self, limit: int = 30) -> list[MarketJournalEntry]:
        stmt = select(MarketJournalEntry).order_by(MarketJournalEntry.date.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_date(self, date: datetime) -> MarketJournalEntry | None:
        from sqlalchemy import func
        stmt = (
            select(MarketJournalEntry)
            .where(func.date(MarketJournalEntry.date) == date.date())
        )
        if self.user_id is not None:
            stmt = stmt.where(MarketJournalEntry.user_id == self.user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ManualOrderRepository:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def create(self, **kwargs) -> ManualOrder:
        kwargs["user_id"] = self.user_id
        order = ManualOrder(**kwargs)
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_all(self, status: str | None = None) -> list[ManualOrder]:
        stmt = (
            select(ManualOrder)
            .where(ManualOrder.user_id == self.user_id)
            .order_by(ManualOrder.created_at.desc())
        )
        if status:
            stmt = stmt.where(ManualOrder.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, order_id: int, status: str, fill_price: float | None = None, fee: float = 0.0) -> None:
        values: dict = {"status": status}
        if fill_price is not None:
            values["fill_price"] = fill_price
            values["fee"] = fee
            values["filled_at"] = datetime.now(timezone.utc)
        stmt = (
            update(ManualOrder)
            .where(ManualOrder.id == order_id)
            .where(ManualOrder.user_id == self.user_id)
            .values(**values)
        )
        await self.session.execute(stmt)

    async def cancel(self, order_id: int) -> bool:
        stmt = (
            update(ManualOrder)
            .where(ManualOrder.id == order_id)
            .where(ManualOrder.user_id == self.user_id)
            .where(ManualOrder.status == "pending")
            .values(status="cancelled")
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0
