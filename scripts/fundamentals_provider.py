"""Longbridge-backed fundamentals without synthetic fallbacks."""

from __future__ import annotations

import os
from typing import Any


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _empty_fundamentals(source: str = "unavailable") -> dict:
    return {
        "pe": None,
        "pb": None,
        "market_cap": None,
        "sector": None,
        "dividend": None,
        "source": source,
    }


def longport_symbol(symbol: str) -> str:
    return symbol if "." in symbol else f"{symbol}.US"


def _quote_context():
    app_key = os.getenv("LONGPORT_APP_KEY", "").strip()
    app_secret = os.getenv("LONGPORT_APP_SECRET", "").strip()
    access_token = os.getenv("LONGPORT_ACCESS_TOKEN", "").strip()
    if not all((app_key, app_secret, access_token)):
        return None
    from longport.openapi import Config, QuoteContext

    return QuoteContext(
        Config(app_key=app_key, app_secret=app_secret, access_token=access_token)
    )


def fetch_fundamentals(
    symbol: str,
    current_price: float,
    quote_context=None,
) -> dict:
    """Fetch current static fundamentals; return explicit N/A values on failure."""
    context = quote_context or _quote_context()
    if context is None:
        return _empty_fundamentals()
    try:
        records = context.static_info([longport_symbol(symbol)])
        if not records:
            return _empty_fundamentals()
        info = records[0]
        eps = _number(getattr(info, "eps_ttm", None))
        bps = _number(getattr(info, "bps", None))
        shares = _number(getattr(info, "total_shares", None))
        dividend_yield = _number(getattr(info, "dividend_yield", None))
        return {
            "pe": round(current_price / eps, 2) if eps and eps > 0 else None,
            "pb": round(current_price / bps, 2) if bps and bps > 0 else None,
            "market_cap": round(current_price * shares, 2) if shares and shares > 0 else None,
            "sector": None,
            "dividend": round(dividend_yield, 2) if dividend_yield is not None else None,
            "source": "longport",
        }
    except Exception:
        return _empty_fundamentals()
