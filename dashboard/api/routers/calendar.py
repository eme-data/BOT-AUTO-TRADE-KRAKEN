"""Economic Calendar – recurring macro-economic and crypto events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from dashboard.api.deps import get_current_user

router = APIRouter(
    prefix="/api/calendar",
    tags=["calendar"],
    dependencies=[Depends(get_current_user)],
)


# ── Known schedules ────────────────────────────────────────────────

# FOMC meeting dates (known 2025-2026 schedule, roughly every 6 weeks)
_FOMC_DATES = [
    # 2025
    (2025, 1, 29), (2025, 3, 19), (2025, 5, 7), (2025, 6, 18),
    (2025, 7, 30), (2025, 9, 17), (2025, 10, 29), (2025, 12, 17),
    # 2026
    (2026, 1, 28), (2026, 3, 18), (2026, 4, 29), (2026, 6, 17),
    (2026, 7, 29), (2026, 9, 16), (2026, 10, 28), (2026, 12, 16),
    # 2027
    (2027, 1, 27), (2027, 3, 17), (2027, 4, 28), (2027, 6, 16),
    (2027, 7, 28), (2027, 9, 15), (2027, 10, 27), (2027, 12, 15),
]

# ECB rate decision dates (roughly monthly, Thursdays)
_ECB_DATES = [
    # 2025
    (2025, 1, 30), (2025, 3, 6), (2025, 4, 17), (2025, 6, 5),
    (2025, 7, 24), (2025, 9, 11), (2025, 10, 30), (2025, 12, 18),
    # 2026
    (2026, 1, 22), (2026, 3, 5), (2026, 4, 16), (2026, 6, 4),
    (2026, 7, 16), (2026, 9, 10), (2026, 10, 29), (2026, 12, 17),
]


def _next_first_friday(after: datetime) -> datetime:
    """Find the first Friday of the next month after `after`."""
    # Move to next month
    if after.month == 12:
        year, month = after.year + 1, 1
    else:
        year, month = after.year, after.month + 1
    # Find first Friday
    d = datetime(year, month, 1, 14, 30, tzinfo=timezone.utc)
    while d.weekday() != 4:  # 4 = Friday
        d += timedelta(days=1)
    return d


def _next_cpi_date(after: datetime) -> datetime:
    """CPI is typically released around the 10th-14th of each month."""
    if after.month == 12:
        year, month = after.year + 1, 1
    else:
        year, month = after.year, after.month + 1
    d = datetime(year, month, 10, 14, 30, tzinfo=timezone.utc)
    # Shift to nearest weekday
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _next_gdp_date(after: datetime) -> datetime:
    """GDP released quarterly: end of Jan, Apr, Jul, Oct."""
    gdp_months = [1, 4, 7, 10]
    for m in gdp_months:
        year = after.year
        d = datetime(year, m, 28, 14, 30, tzinfo=timezone.utc)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        if d > after:
            return d
    # Next year
    d = datetime(after.year + 1, 1, 28, 14, 30, tzinfo=timezone.utc)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _generate_events(days: int) -> list[dict]:
    """Generate upcoming economic events for the next N days."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    events: list[dict] = []

    # FOMC meetings
    for y, m, d in _FOMC_DATES:
        dt = datetime(y, m, d, 20, 0, tzinfo=timezone.utc)
        if now - timedelta(days=1) <= dt <= cutoff:
            events.append({
                "date": dt.isoformat(),
                "title": "FOMC - Decision taux Fed",
                "description": "Le Federal Open Market Committee annonce sa decision sur les taux directeurs americains.",
                "impact": "high",
                "category": "fed",
            })

    # ECB rate decisions
    for y, m, d in _ECB_DATES:
        dt = datetime(y, m, d, 13, 45, tzinfo=timezone.utc)
        if now - timedelta(days=1) <= dt <= cutoff:
            events.append({
                "date": dt.isoformat(),
                "title": "BCE - Decision taux directeurs",
                "description": "La Banque Centrale Europeenne annonce sa decision sur les taux directeurs de la zone euro.",
                "impact": "high",
                "category": "fed",
            })

    # CPI releases (monthly, ~10th-14th)
    cursor = now - timedelta(days=5)
    for _ in range(max(days // 28 + 2, 3)):
        cpi_dt = _next_cpi_date(cursor)
        if now - timedelta(days=1) <= cpi_dt <= cutoff:
            events.append({
                "date": cpi_dt.isoformat(),
                "title": "Publication CPI (Inflation US)",
                "description": "L'indice des prix a la consommation americain est un indicateur cle de l'inflation. Fort impact sur les marches crypto.",
                "impact": "high",
                "category": "inflation",
            })
        cursor = cpi_dt

    # Jobs report (first Friday of each month)
    cursor = now - timedelta(days=5)
    for _ in range(max(days // 28 + 2, 3)):
        jobs_dt = _next_first_friday(cursor)
        if now - timedelta(days=1) <= jobs_dt <= cutoff:
            events.append({
                "date": jobs_dt.isoformat(),
                "title": "Rapport emploi US (NFP)",
                "description": "Le rapport mensuel sur l'emploi non-agricole (Non-Farm Payrolls) influence directement les attentes sur les taux Fed.",
                "impact": "high",
                "category": "employment",
            })
        cursor = jobs_dt

    # GDP releases (quarterly)
    cursor = now - timedelta(days=5)
    for _ in range(max(days // 90 + 2, 3)):
        gdp_dt = _next_gdp_date(cursor)
        if now - timedelta(days=1) <= gdp_dt <= cutoff:
            events.append({
                "date": gdp_dt.isoformat(),
                "title": "Publication PIB US (GDP)",
                "description": "Le produit interieur brut americain trimestriel mesure la croissance economique.",
                "impact": "medium",
                "category": "gdp",
            })
        cursor = gdp_dt + timedelta(days=1)

    # Bitcoin halving (next estimated: ~April 2028)
    btc_halving = datetime(2028, 4, 15, 0, 0, tzinfo=timezone.utc)
    if now - timedelta(days=1) <= btc_halving <= cutoff:
        events.append({
            "date": btc_halving.isoformat(),
            "title": "Bitcoin Halving",
            "description": "La recompense de minage Bitcoin est divisee par deux. Evenement majeur historiquement haussier.",
            "impact": "high",
            "category": "crypto",
        })

    # Ethereum major upgrades / recurring crypto events
    # Add quarterly crypto options expiry (last Friday of March, June, September, December)
    options_months = [3, 6, 9, 12]
    for year in [now.year, now.year + 1]:
        for m in options_months:
            # Last Friday of the month
            if m == 12:
                last_day = datetime(year, 12, 31, 10, 0, tzinfo=timezone.utc)
            else:
                last_day = datetime(year, m + 1, 1, 10, 0, tzinfo=timezone.utc) - timedelta(days=1)
            while last_day.weekday() != 4:
                last_day -= timedelta(days=1)
            if now - timedelta(days=1) <= last_day <= cutoff:
                events.append({
                    "date": last_day.isoformat(),
                    "title": "Expiration options crypto trimestrielle",
                    "description": "Expiration trimestrielle majeure des options BTC et ETH. Volatilite accrue attendue.",
                    "impact": "medium",
                    "category": "crypto",
                })

    # Sort by date
    events.sort(key=lambda e: e["date"])
    return events


@router.get("/events")
async def get_events(days: int = Query(30, ge=1, le=365)):
    """Get upcoming economic events for the next N days."""
    return _generate_events(days)


@router.get("/today")
async def get_today_events():
    """Get events happening today or within the next 48 hours."""
    now = datetime.now(timezone.utc)
    all_events = _generate_events(days=3)
    cutoff = now + timedelta(hours=48)
    return [
        e for e in all_events
        if datetime.fromisoformat(e["date"]) <= cutoff
    ]
