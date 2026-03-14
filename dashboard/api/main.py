"""FastAPI dashboard application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.api.routers import (
    ai,
    auth,
    bot_control,
    markets,
    settings_router,
    trades,
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
app.include_router(auth.router)
app.include_router(bot_control.router)
app.include_router(trades.router)
app.include_router(settings_router.router)
app.include_router(markets.router)
app.include_router(ws.router)
app.include_router(ai.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
