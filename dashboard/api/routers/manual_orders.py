"""Manual order placement and management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from bot.config import settings
from bot.db.repository import ManualOrderRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/orders",
    tags=["orders"],
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


# ── Request models ───────────────────────────────────

class OrderCreate(BaseModel):
    pair: str
    direction: str  # buy / sell
    order_type: str  # market / limit / stop_limit
    size: float
    price: float | None = None
    stop_price: float | None = None


# ── Endpoints ────────────────────────────────────────

@router.get("/")
async def list_orders(
    status_filter: str | None = None,
    user_id: int = Depends(get_user_id),
):
    """List manual orders, optionally filtered by status."""
    async with get_session() as session:
        repo = ManualOrderRepository(session, user_id=user_id)
        orders = await repo.get_all(status=status_filter)
    return [
        {
            "id": o.id,
            "pair": o.pair,
            "direction": o.direction,
            "order_type": o.order_type,
            "size": o.size,
            "price": o.price,
            "stop_price": o.stop_price,
            "status": o.status,
            "order_id": o.order_id,
            "fill_price": o.fill_price,
            "fee": o.fee,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
        }
        for o in orders
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_order(body: OrderCreate, user_id: int = Depends(get_user_id)):
    """Place a manual order.

    Market orders are executed immediately via broker.
    Limit / stop-limit orders are saved as pending.
    """
    if body.direction not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="direction must be 'buy' or 'sell'",
        )
    if body.order_type not in ("market", "limit", "stop_limit"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order_type must be 'market', 'limit', or 'stop_limit'",
        )
    if body.size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="size must be positive",
        )
    if body.order_type == "limit" and body.price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="price is required for limit orders",
        )
    if body.order_type == "stop_limit":
        if body.price is None or body.stop_price is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="price and stop_price are required for stop-limit orders",
            )

    # For market orders, execute immediately
    if body.order_type == "market":
        from bot.broker.models import Direction, OrderRequest, OrderType

        broker = await _get_broker(user_id)
        try:
            order_req = OrderRequest(
                pair=body.pair,
                direction=Direction.BUY if body.direction == "buy" else Direction.SELL,
                size=body.size,
                order_type=OrderType.MARKET,
            )
            result = await broker.open_position(order_req)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to execute market order: {str(exc)}",
            )
        finally:
            await broker.disconnect()

        # Save the filled order to DB
        async with get_session() as session:
            repo = ManualOrderRepository(session, user_id=user_id)
            order = await repo.create(
                pair=body.pair,
                direction=body.direction,
                order_type="market",
                size=body.size,
                status="filled",
                order_id=result.order_id,
                fill_price=result.price,
                fee=result.fee,
                filled_at=datetime.now(timezone.utc),
            )
            return {
                "id": order.id,
                "pair": order.pair,
                "direction": order.direction,
                "order_type": order.order_type,
                "size": order.size,
                "status": "filled",
                "order_id": result.order_id,
                "fill_price": result.price,
                "fee": result.fee,
                "filled_at": datetime.now(timezone.utc).isoformat(),
            }

    # For limit / stop_limit, save as pending
    async with get_session() as session:
        repo = ManualOrderRepository(session, user_id=user_id)
        order = await repo.create(
            pair=body.pair,
            direction=body.direction,
            order_type=body.order_type,
            size=body.size,
            price=body.price,
            stop_price=body.stop_price,
            status="pending",
        )
        return {
            "id": order.id,
            "pair": order.pair,
            "direction": order.direction,
            "order_type": order.order_type,
            "size": order.size,
            "price": order.price,
            "stop_price": order.stop_price,
            "status": "pending",
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }


@router.delete("/{order_id}")
async def cancel_order(order_id: int, user_id: int = Depends(get_user_id)):
    """Cancel a pending order."""
    async with get_session() as session:
        repo = ManualOrderRepository(session, user_id=user_id)
        cancelled = await repo.cancel(order_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found or already filled/cancelled",
        )
    return {"message": "Order cancelled"}
