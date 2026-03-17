"""Simple Redis-based rate limiting middleware."""
from __future__ import annotations
import os
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Rate limits: requests per minute
RATE_LIMITS = {
    "/api/auth/login": 10,       # Login: 10/min
    "/api/backtest/run": 5,      # Backtest: 5/min (heavy)
    "/api/ai/": 10,              # AI calls: 10/min
    "/api/market-journal/generate": 3,  # Journal gen: 3/min
    "/api/portfolio/rebalance": 3,      # Rebalance: 3/min
    "default": 120,              # Everything else: 120/min
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip non-API routes and WebSocket
        if not request.url.path.startswith("/api/") or request.url.path.startswith("/api/ws"):
            return await call_next(request)

        # Determine rate limit
        limit = RATE_LIMITS.get("default", 120)
        for prefix, lim in RATE_LIMITS.items():
            if prefix != "default" and request.url.path.startswith(prefix):
                limit = lim
                break

        # Build key from IP
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}:{request.url.path.split('/')[2]}"  # Group by /api/{resource}

        try:
            r = redis.from_url(REDIS_URL, decode_responses=True)
            current = await r.get(key)
            if current and int(current) >= limit:
                await r.close()
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please try again later."},
                    headers={"Retry-After": "60"},
                )
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)  # 1 minute window
            await pipe.execute()
            await r.close()
        except Exception:
            pass  # If Redis fails, allow the request

        response = await call_next(request)
        return response
