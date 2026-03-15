"""Portfolio holdings, target allocations, and auto-rebalancing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from bot.config import settings
from bot.db.repository import PortfolioTargetRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id, require_admin

router = APIRouter(
    prefix="/api/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(get_current_user)],
)


# ── Helpers ──────────────────────────────────────────

async def _get_broker(user_id: int):
    """Instantiate a KrakenRestClient with the user's credentials."""
    from bot.crypto import decrypt
    from bot.db.repository import SettingsRepository

    try:
        async with get_session() as session:
            repo = SettingsRepository(session, user_id=user_id)
            db_values = await repo.get_decrypted_values(decrypt)
    except Exception:
        db_values = {}

    api_key = db_values.get("kraken_api_key", settings.kraken_api_key)
    api_secret = db_values.get("kraken_api_secret", settings.kraken_api_secret)

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kraken credentials not configured",
        )

    from bot.broker.kraken_rest import KrakenRestClient

    broker = KrakenRestClient(api_key=api_key, api_secret=api_secret)
    await broker.connect()
    return broker


async def _get_holdings(user_id: int) -> tuple[list[dict], float]:
    """Return (holdings_list, total_value) for the user's account."""
    broker = await _get_broker(user_id)
    try:
        balance = await broker.exchange.fetch_balance()
        holdings: list[dict] = []
        total_value = 0.0

        # Process USD/fiat balance
        for fiat in ("USD", "ZUSD"):
            amt = float(balance.get("total", {}).get(fiat, 0) or 0)
            if amt > 0:
                holdings.append({
                    "pair": "USD",
                    "quantity": amt,
                    "current_price": 1.0,
                    "value_usd": amt,
                    "allocation_pct": 0.0,  # computed later
                })
                total_value += amt

        # Process crypto holdings
        for currency, amount in balance.get("total", {}).items():
            if currency in ("USD", "EUR", "ZUSD", "ZEUR"):
                continue
            total_amt = float(amount) if amount else 0.0
            if total_amt <= 0:
                continue

            pair = f"{currency}/USD"
            try:
                ticker = await broker.get_ticker(pair)
                current_price = ticker.last
            except Exception:
                current_price = 0.0

            value_usd = total_amt * current_price
            if value_usd < 0.01:
                continue

            holdings.append({
                "pair": pair,
                "quantity": total_amt,
                "current_price": current_price,
                "value_usd": round(value_usd, 2),
                "allocation_pct": 0.0,
            })
            total_value += value_usd

        # Compute allocation percentages
        if total_value > 0:
            for h in holdings:
                h["allocation_pct"] = round(h["value_usd"] / total_value * 100, 2)

        return holdings, round(total_value, 2)
    finally:
        await broker.disconnect()


# ── Request models ───────────────────────────────────

class TargetItem(BaseModel):
    pair: str
    target_pct: float


class SetTargetsBody(BaseModel):
    targets: list[TargetItem]


# ── Endpoints ────────────────────────────────────────

@router.get("/holdings")
async def get_holdings(user_id: int = Depends(get_user_id)):
    """Get current portfolio holdings with prices and allocations."""
    try:
        holdings, total_value = await _get_holdings(user_id)
        return {"holdings": holdings, "total_value": total_value}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch holdings: {str(exc)}",
        )


@router.get("/targets")
async def get_targets(user_id: int = Depends(get_user_id)):
    """Get user's target allocations."""
    async with get_session() as session:
        repo = PortfolioTargetRepository(session, user_id=user_id)
        targets = await repo.get_all()
    return [
        {
            "id": t.id,
            "pair": t.pair,
            "target_pct": t.target_pct,
            "active": t.active,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in targets
    ]


@router.put("/targets")
async def set_targets(body: SetTargetsBody, user_id: int = Depends(get_user_id)):
    """Set target allocations. Percentages must sum to <= 100."""
    total_pct = sum(t.target_pct for t in body.targets)
    if total_pct > 100.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Total percentage ({total_pct}%) exceeds 100%",
        )
    for t in body.targets:
        if t.target_pct < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Negative percentage for {t.pair}",
            )

    async with get_session() as session:
        repo = PortfolioTargetRepository(session, user_id=user_id)
        await repo.set_targets([
            {"pair": t.pair, "target_pct": t.target_pct} for t in body.targets
        ])

    return {"message": "Targets updated", "total_pct": total_pct}


@router.get("/rebalance-preview")
async def rebalance_preview(user_id: int = Depends(get_user_id)):
    """Preview trades needed to rebalance toward targets."""
    holdings, total_value = await _get_holdings(user_id)

    async with get_session() as session:
        repo = PortfolioTargetRepository(session, user_id=user_id)
        targets = await repo.get_all()

    if not targets:
        return {"trades": [], "message": "No targets configured"}

    # Build current allocation map
    current_map: dict[str, float] = {}
    for h in holdings:
        current_map[h["pair"]] = h["allocation_pct"]

    trades = []
    for t in targets:
        current_pct = current_map.get(t.pair, 0.0)
        diff_pct = t.target_pct - current_pct
        amount_usd = round(abs(diff_pct) / 100 * total_value, 2)

        if abs(diff_pct) < 0.5:
            continue  # skip negligible differences

        trades.append({
            "pair": t.pair,
            "current_pct": round(current_pct, 2),
            "target_pct": t.target_pct,
            "diff_pct": round(diff_pct, 2),
            "action": "buy" if diff_pct > 0 else "sell",
            "amount_usd": amount_usd,
        })

    return {"trades": trades, "total_value": total_value}


@router.post("/rebalance", dependencies=[Depends(require_admin)])
async def execute_rebalance(user_id: int = Depends(get_user_id)):
    """Execute rebalance trades to match target allocations (admin only)."""
    from bot.broker.models import Direction, OrderRequest, OrderType

    holdings, total_value = await _get_holdings(user_id)

    async with get_session() as session:
        repo = PortfolioTargetRepository(session, user_id=user_id)
        targets = await repo.get_all()

    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No targets configured",
        )

    # Build current allocation map
    current_map: dict[str, float] = {}
    price_map: dict[str, float] = {}
    for h in holdings:
        current_map[h["pair"]] = h["allocation_pct"]
        price_map[h["pair"]] = h["current_price"]

    # Compute needed trades
    needed_trades = []
    for t in targets:
        current_pct = current_map.get(t.pair, 0.0)
        diff_pct = t.target_pct - current_pct
        amount_usd = abs(diff_pct) / 100 * total_value

        if abs(diff_pct) < 0.5 or amount_usd < 1.0:
            continue

        price = price_map.get(t.pair, 0.0)
        if t.pair == "USD" or price <= 0:
            continue

        size = amount_usd / price

        needed_trades.append({
            "pair": t.pair,
            "direction": Direction.BUY if diff_pct > 0 else Direction.SELL,
            "size": size,
            "amount_usd": amount_usd,
        })

    if not needed_trades:
        return {"message": "Portfolio already balanced", "executed": []}

    # Execute trades
    broker = await _get_broker(user_id)
    executed = []
    errors = []
    try:
        for trade in needed_trades:
            try:
                order = OrderRequest(
                    pair=trade["pair"],
                    direction=trade["direction"],
                    size=round(trade["size"], 8),
                    order_type=OrderType.MARKET,
                )
                result = await broker.open_position(order)
                executed.append({
                    "pair": trade["pair"],
                    "action": trade["direction"].value,
                    "size": trade["size"],
                    "amount_usd": trade["amount_usd"],
                    "order_id": result.order_id,
                    "fill_price": result.price,
                    "fee": result.fee,
                })
            except Exception as exc:
                errors.append({
                    "pair": trade["pair"],
                    "error": str(exc),
                })
    finally:
        await broker.disconnect()

    return {
        "message": f"Rebalance complete: {len(executed)} trades executed",
        "executed": executed,
        "errors": errors,
    }
