"""FastAPI dashboard application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.api.routers import (
    ai,
    alerts,
    analytics,
    audit,
    auth,
    backtest,
    bot_control,
    calendar,
    copy_trading,
    dca,
    fees,
    manual_orders,
    market_journal,
    markets,
    permissions,
    polymarket,
    portfolio,
    push,
    reports,
    sessions,
    settings_router,
    strategies,
    targets,
    telegram_webhook,
    trades,
    users,
    ws,
)

app = FastAPI(
    title="Kraken Trading Bot – Dashboard",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(analytics.router)
app.include_router(audit.router)
app.include_router(auth.router)
app.include_router(bot_control.router)
app.include_router(trades.router)
app.include_router(settings_router.router)
app.include_router(markets.router)
app.include_router(ws.router)
app.include_router(ai.router)
app.include_router(strategies.router)
app.include_router(users.router)
app.include_router(polymarket.router)
app.include_router(push.router)
app.include_router(alerts.router)
app.include_router(backtest.router)
app.include_router(copy_trading.router)
app.include_router(dca.router)
app.include_router(reports.router)
app.include_router(calendar.router)
app.include_router(market_journal.router)
app.include_router(manual_orders.router)
app.include_router(permissions.router)
app.include_router(portfolio.router)
app.include_router(telegram_webhook.router)
app.include_router(fees.router)
app.include_router(targets.router)
app.include_router(sessions.router)


# Rate limiting middleware
try:
    from dashboard.api.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
except ImportError:
    pass


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Serve React frontend ─────────────────────────────
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        """Serve React SPA – all non-API routes return index.html."""
        file_path = _FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_FRONTEND_DIR / "index.html")
