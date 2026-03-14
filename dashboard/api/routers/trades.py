"""Trade history, open positions, stats, and export endpoints."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from bot.db.repository import TradeRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/trades",
    tags=["trades"],
    dependencies=[Depends(get_current_user)],
)


def _trade_dict(t):
    return {
        "id": t.id,
        "order_id": t.order_id,
        "pair": t.pair,
        "direction": t.direction,
        "size": t.size,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "profit": t.profit,
        "fee": t.fee,
        "status": t.status,
        "strategy": t.strategy,
        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    }


async def _fetch_trades(user_id: int, days: Optional[int] = None):
    """Fetch trades filtered by number of days (None = all)."""
    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        if days is not None and days > 0:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            return await repo.get_trades_since(since)
        return await repo.get_recent_trades(limit=10_000)


def _compute_stats(trades):
    """Compute summary statistics from a list of trade model objects."""
    closed = [t for t in trades if t.status == "CLOSED" and t.profit is not None]
    total = len(closed)
    winning = [t for t in closed if t.profit > 0]
    losing = [t for t in closed if t.profit <= 0]
    total_pnl = sum(t.profit for t in closed)
    total_fees = sum(t.fee or 0 for t in trades)
    win_rate = (len(winning) / total * 100) if total > 0 else 0.0
    avg_win = (sum(t.profit for t in winning) / len(winning)) if winning else 0.0
    avg_loss = (sum(t.profit for t in losing) / len(losing)) if losing else 0.0
    best_trade = max((t.profit for t in closed), default=0.0)
    worst_trade = min((t.profit for t in closed), default=0.0)
    gross_wins = sum(t.profit for t in winning)
    gross_losses = abs(sum(t.profit for t in losing))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf") if gross_wins > 0 else 0.0

    return {
        "total_trades": total,
        "winning": len(winning),
        "losing": len(losing),
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 2),
        "win_rate": round(win_rate, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
    }


# ─── existing endpoints ─────────────────────────────────────────────

@router.get("/")
async def list_trades(limit: int = 50, user_id: int = Depends(get_user_id)):
    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        trades = await repo.get_recent_trades(limit=limit)
        return [_trade_dict(t) for t in trades]


@router.get("/open")
async def open_trades(user_id: int = Depends(get_user_id)):
    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        trades = await repo.get_open_trades()
        return [
            {
                "id": t.id,
                "order_id": t.order_id,
                "pair": t.pair,
                "direction": t.direction,
                "size": t.size,
                "entry_price": t.entry_price,
                "strategy": t.strategy,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            }
            for t in trades
        ]


# ─── stats endpoint ─────────────────────────────────────────────────

@router.get("/stats")
async def trade_stats(days: Optional[int] = Query(30), user_id: int = Depends(get_user_id)):
    trades = await _fetch_trades(user_id, days)
    return _compute_stats(trades)


# ─── CSV export ──────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_csv(days: Optional[int] = Query(30), user_id: int = Depends(get_user_id)):
    trades = await _fetch_trades(user_id, days)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Date", "Pair", "Direction", "Size", "Entry Price",
        "Exit Price", "Profit", "Fee", "Status", "Strategy",
    ])
    for t in trades:
        writer.writerow([
            t.opened_at.isoformat() if t.opened_at else "",
            t.pair,
            t.direction,
            t.size,
            t.entry_price,
            t.exit_price if t.exit_price is not None else "",
            round(t.profit, 2) if t.profit is not None else "",
            round(t.fee, 2) if t.fee else "0.00",
            t.status,
            t.strategy or "",
        ])

    buf.seek(0)
    filename = f"trades_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── PDF export ──────────────────────────────────────────────────────

@router.get("/export/pdf")
async def export_pdf(days: Optional[int] = Query(30), user_id: int = Depends(get_user_id)):
    trades = await _fetch_trades(user_id, days)
    stats = _compute_stats(trades)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6 * mm,
    )

    elements = []

    # Title
    elements.append(Paragraph("Trade Report &mdash; Altior Holding", title_style))

    # Date range
    now = datetime.now(timezone.utc)
    if days:
        start = now - timedelta(days=days)
        range_text = f"Period: {start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')} ({days} days)"
    else:
        range_text = f"All trades as of {now.strftime('%Y-%m-%d %H:%M UTC')}"
    elements.append(Paragraph(range_text, styles["Normal"]))
    elements.append(Spacer(1, 4 * mm))

    # Summary stats
    pf_display = f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "N/A"
    summary_lines = [
        f"<b>Total trades:</b> {stats['total_trades']}  |  "
        f"<b>Winning:</b> {stats['winning']}  |  "
        f"<b>Losing:</b> {stats['losing']}  |  "
        f"<b>Win rate:</b> {stats['win_rate']}%",
        f"<b>Total P&amp;L:</b> ${stats['total_pnl']:.2f}  |  "
        f"<b>Total fees:</b> ${stats['total_fees']:.2f}  |  "
        f"<b>Profit factor:</b> {pf_display}",
        f"<b>Best trade:</b> ${stats['best_trade']:.2f}  |  "
        f"<b>Worst trade:</b> ${stats['worst_trade']:.2f}  |  "
        f"<b>Avg win:</b> ${stats['avg_win']:.2f}  |  "
        f"<b>Avg loss:</b> ${stats['avg_loss']:.2f}",
    ]
    for line in summary_lines:
        elements.append(Paragraph(line, styles["Normal"]))
    elements.append(Spacer(1, 6 * mm))

    # Trade table
    header = [
        "Date", "Pair", "Dir", "Size", "Entry",
        "Exit", "Profit", "Fee", "Status", "Strategy",
    ]
    data = [header]
    for t in trades:
        data.append([
            t.opened_at.strftime("%Y-%m-%d %H:%M") if t.opened_at else "",
            t.pair,
            t.direction.upper(),
            f"{t.size}",
            f"{t.entry_price:.2f}",
            f"{t.exit_price:.2f}" if t.exit_price is not None else "-",
            f"{t.profit:.2f}" if t.profit is not None else "-",
            f"{t.fee:.2f}" if t.fee else "0.00",
            t.status,
            t.strategy or "",
        ])

    col_widths = [36 * mm, 22 * mm, 12 * mm, 18 * mm, 22 * mm, 22 * mm, 22 * mm, 18 * mm, 18 * mm, 28 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (3, 0), (7, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(table)

    doc.build(elements)
    buf.seek(0)

    filename = f"trade_report_{now.strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
