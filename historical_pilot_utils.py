"""
================================================================================
AHAD AI - Historical Market Pilot - Utilities
================================================================================

Standalone HTTP + math utilities for the pilot. Zero imports from bot.py,
zero imports from any Research module (including independent_market_
indicators.py) - the indicator functions below are COPIED, not imported,
per the explicit isolation requirement: the pilot must run with zero
dependency on the rest of the project, and nothing in the project may
depend on the pilot.

CLOSED CANDLES ONLY throughout: every candle-returning function here
filters to confirm=="1" before returning - callers never see an
unconfirmed candle.
"""

import time
import requests

from historical_pilot_config import (
    OKX_BASE_URL, CANDLES_HISTORY_ENDPOINT, INSTRUMENTS_ENDPOINT,
    FUNDING_RATE_HISTORY_ENDPOINT, OPEN_INTEREST_HISTORY_ENDPOINT,
    REQUEST_DELAY_SECONDS, MAX_RETRIES_PER_REQUEST, BACKOFF_BASE_SECONDS,
)

# Mutable counters the caller can inspect after a pilot run - simple
# module-level state, adequate for a single manual-run script.
STATS = {
    "total_requests": 0, "retries": 0, "http_429": 0, "failures": 0,
}


def _request_with_retry(url, params):
    """
    GET with bounded retry + exponential backoff. Returns the parsed
    JSON dict on success, or None if every retry is exhausted - never
    raises, never loops unbounded (hard cap: MAX_RETRIES_PER_REQUEST).
    """
    last_error = None
    for attempt in range(MAX_RETRIES_PER_REQUEST):
        STATS["total_requests"] += 1
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                STATS["http_429"] += 1
                STATS["retries"] += 1
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                continue
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                STATS["retries"] += 1
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                continue
            data = resp.json()
            if data.get("code") != "0":
                last_error = f"OKX code={data.get('code')} msg={data.get('msg')}"
                STATS["retries"] += 1
                time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                continue
            time.sleep(REQUEST_DELAY_SECONDS)
            return data
        except Exception as e:
            last_error = str(e)
            STATS["retries"] += 1
            time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))

    STATS["failures"] += 1
    print(f"⚠️ Pilot: request failed after {MAX_RETRIES_PER_REQUEST} attempts - {last_error}")
    return None


def fetch_historical_candles_page(symbol, bar, before=None, after=None, limit=100):
    """
    One page of history-candles. `before`/`after` are OKX pagination
    cursors (ms timestamps as strings) - `after` moves further back in
    time (older), `before` moves forward (newer). Returns CLOSED
    candles only (confirm=="1"), oldest-first, as a list of dicts, or
    [] on failure/empty.
    """
    params = {"instId": symbol, "bar": bar, "limit": limit}
    if before:
        params["before"] = before
    if after:
        params["after"] = after

    data = _request_with_retry(f"{OKX_BASE_URL}{CANDLES_HISTORY_ENDPOINT}", params)
    if data is None:
        return []
    raw = data.get("data", [])
    if not raw:
        return []
    closed = [c for c in raw if len(c) > 8 and c[8] == "1"]
    closed = list(reversed(closed))  # OKX returns newest-first; we want oldest-first
    return [
        {"ts": c[0], "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
         "close": float(c[4]), "volume": float(c[5]), "confirm": c[8]}
        for c in closed
    ]


def fetch_candles_paginated(symbol, bar, start_ts_ms, end_ts_ms, limit=100):
    """
    Walks backward from end_ts_ms to start_ts_ms using the `after`
    cursor, one page at a time, until the window is covered or no more
    data is returned. Returns all CLOSED candles in the window,
    oldest-first, de-duplicated by timestamp.
    """
    all_candles = {}
    cursor_after = str(end_ts_ms)
    pages = 0
    max_pages = 200  # hard safety cap - never an unbounded loop

    while pages < max_pages:
        page = fetch_historical_candles_page(symbol, bar, after=cursor_after, limit=limit)
        pages += 1
        if not page:
            break
        for c in page:
            all_candles[c["ts"]] = c
        oldest_ts_this_page = int(page[0]["ts"])
        if oldest_ts_this_page <= start_ts_ms:
            break
        cursor_after = page[0]["ts"]

    result = sorted(all_candles.values(), key=lambda c: int(c["ts"]))
    return [c for c in result if start_ts_ms <= int(c["ts"]) <= end_ts_ms]


def test_historical_universe():
    """
    Tests /public/instruments WITHOUT instId - the exact test that
    resolves whether Survivorship Bias can be mitigated from OKX
    directly. Returns (success: bool, instruments: list, distinct_states: set).
    """
    data = _request_with_retry(f"{OKX_BASE_URL}{INSTRUMENTS_ENDPOINT}", {"instType": "SWAP"})
    if data is None:
        return False, [], set()
    instruments = data.get("data", [])
    states = set(i.get("state") for i in instruments)
    return True, instruments, states


def fetch_funding_rate_history(symbol, limit=10):
    """Attempts historical funding rate. Returns [] if unavailable -
    never fabricates a value."""
    data = _request_with_retry(f"{OKX_BASE_URL}{FUNDING_RATE_HISTORY_ENDPOINT}",
                                {"instId": symbol, "limit": limit})
    if data is None:
        return []
    return data.get("data", [])


def fetch_open_interest_history(symbol, period="1H", limit=10):
    """Attempts historical open interest. Returns [] if unavailable -
    never fabricates a value."""
    data = _request_with_retry(f"{OKX_BASE_URL}{OPEN_INTEREST_HISTORY_ENDPOINT}",
                                {"instId": symbol, "period": period, "limit": limit})
    if data is None:
        return []
    return data.get("data", [])


# ================================================
# Pure indicator functions - COPIED from independent_market_indicators.py
# (which itself copied them from bot.py). Kept identical for consistency
# with the rest of the project's Research Lab, but duplicated here
# deliberately so this pilot has zero import dependency on that file.
# ================================================

def ema(values, period):
    if len(values) < period:
        return values[-1] if values else 0
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles):
    if len(candles) < 2:
        return 0
    trs = []
    for i in range(1, len(candles)):
        high, low = candles[i]["high"], candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0


def macd_simple(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow:
        return None
    return ema(closes, fast) - ema(closes, slow)


def smart_money(candles):
    if len(candles) < 50:
        return {"flow": None, "volume_acceleration": None}
    volumes = [c["volume"] for c in candles]
    recent_5 = sum(volumes[-5:])
    avg_50 = sum(volumes[-50:]) / 50
    flow = (recent_5 / (avg_50 * 5)) if avg_50 > 0 else None
    avg_20 = sum(volumes[-20:]) / 20
    volume_acceleration = (volumes[-1] / avg_20) if avg_20 > 0 else None
    return {"flow": flow, "volume_acceleration": volume_acceleration}


def volatility_engine(candles):
    if len(candles) < 60:
        return {"score": None, "status": "UNKNOWN"}
    atr_now = atr(candles[-14:])
    atr_old = atr(candles[-60:-46])
    if atr_old == 0:
        compression = None
    else:
        compression = max(0, min(100, (1 - (atr_now / atr_old)) * 100))
    if compression is None:
        status = "UNKNOWN"
    elif compression >= 70:
        status = "SPRING LOADED"
    elif compression >= 50:
        status = "BUILDING PRESSURE"
    elif compression >= 30:
        status = "NORMAL COMPRESSION"
    else:
        status = "EXPANDING"
    return {"score": round(compression) if compression is not None else None, "status": status}


def market_regime(candles):
    if len(candles) < 150:
        return "UNKNOWN"
    closes = [c["close"] for c in candles]
    ema20_val = ema(closes, 20)
    ema50_val = ema(closes, 50)
    price = closes[-1]
    comp = volatility_engine(candles)
    if comp["status"] in ("SPRING LOADED", "BUILDING PRESSURE"):
        return "COMPRESSION"
    if price > ema20_val > ema50_val or price < ema20_val < ema50_val:
        return "TRENDING"
    if comp["status"] == "EXPANDING":
        return "MIXED"
    return "RANGING"


def momentum_score_independent(candles):
    if len(candles) < 20:
        return None
    closes = [c["close"] for c in candles]
    if len(closes) < 10:
        return None
    price_change_5 = ((closes[-1] - closes[-5]) / closes[-5]) * 100
    price_change_10 = ((closes[-1] - closes[-10]) / closes[-10]) * 100
    price_velocity = (price_change_5 * 0.6) + (price_change_10 * 0.4)
    sm = smart_money(candles)
    volume_acceleration = sm.get("volume_acceleration") or 0
    recent_high = max(c["high"] for c in candles[-20:])
    recent_low = min(c["low"] for c in candles[-20:])
    range_width = recent_high - recent_low
    breakout_strength = ((closes[-1] - recent_low) / range_width * 100) if range_width > 0 else 50
    score = 0
    if abs(price_velocity) > 3: score += 40
    elif abs(price_velocity) > 1: score += 25
    elif abs(price_velocity) > 0: score += 10
    if volume_acceleration > 2: score += 30
    elif volume_acceleration > 1.5: score += 20
    elif volume_acceleration > 1.2: score += 10
    if breakout_strength > 80 or breakout_strength < 20: score += 30
    elif breakout_strength > 60 or breakout_strength < 40: score += 20
    elif breakout_strength > 50 or breakout_strength < 50: score += 10
    return min(100, score)


def compute_indicators(candles_15m):
    """One flat dict of derived indicators from a 15m candle window -
    None for any indicator whose minimum candle requirement isn't met,
    never a misleading fallback."""
    closes = [c["close"] for c in candles_15m]
    sm = smart_money(candles_15m) if candles_15m else {"flow": None, "volume_acceleration": None}
    comp = volatility_engine(candles_15m) if candles_15m else {"score": None, "status": "UNKNOWN"}
    return {
        "rsi_15m": rsi(closes) if closes else None,
        "flow": sm.get("flow"),
        "volume_ratio": sm.get("volume_acceleration"),
        "momentum_score": momentum_score_independent(candles_15m) if candles_15m else None,
        "ema20": ema(closes, 20) if closes else None,
        "ema50": ema(closes, 50) if closes else None,
        "ema200": ema(closes, 200) if closes else None,
        "macd": macd_simple(closes) if closes else None,
        "atr": atr(candles_15m) if candles_15m else None,
        "compression_status": comp.get("status"),
        "market_regime": market_regime(candles_15m) if candles_15m else "UNKNOWN",
        "candles_used": len(candles_15m),
    }
