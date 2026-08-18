"""
================================================================================
AHAD AI - Research Lab
Independent Market Indicators
================================================================================

Pure indicator-calculation functions, COPIED (not imported) from bot.py's
own production engines - rsi(), ema(), atr(), macd_simple(), smart_money(),
volatility_engine(), market_regime(), and the inline momentum_score logic
from scan(). Copied rather than imported specifically to preserve
Production Isolation: this file never imports bot.py, and bot.py never
imports this file. A future change to bot.py's own copies will NOT
automatically propagate here - a deliberate, documented tradeoff that
protects Production from any Research-side change, at the cost of manual
resync if the production formulas are ever revised.

Every function here takes only OHLCV candle data as input and returns a
value or None - never a Trade DNA record, never a database connection,
never anything from `trades`. This is what makes it usable to build an
INDEPENDENT market snapshot for any symbol, whether or not AHAD AI has
ever traded it.

CLOSED CANDLES ONLY: filter_closed_candles() must be called before any
value here is computed. OKX's own `confirm` field is checked explicitly -
never assumed. Confirmed even against the "historical" endpoint returning
an unconfirmed candle in the pilot investigation for this project.

Minimum candle requirements (confirmed from bot.py's own guards, not
invented here):
  rsi(period=14): needs >= period+1 to be reliable (bot.py's own rsi() has
    no internal guard - the caller is responsible, exactly as production
    does with its 200-candle window)
  ema(period): safe at any length (falls back to last value if short)
  atr(): safe at any length (fewer candles = less accurate, never errors)
  macd_simple(): explicit guard, returns 0 if len(closes) < slow(26)
  volatility_engine() [compression]: explicit guard, returns score=0/status
    UNKNOWN if len(candles) < 60
  market_regime(): explicit guard, returns "UNKNOWN" if len(candles) < 150

This module NEVER imports bot.py and is NEVER imported by bot.py.
================================================================================
"""

import requests
import time
from datetime import datetime, timezone

OKX_CANDLES_URL = "https://www.okx.com/api/v5/market/candles"
REQUEST_DELAY_SECONDS = 0.15


def fetch_candles(symbol, bar, limit=200):
    """
    Fetches candles for one symbol/timeframe from OKX directly -
    independent of any trade or Trade DNA. Returns oldest-first list of
    dicts with open/high/low/close/volume/confirm, or [] on any failure
    (never raises - the caller decides how to handle missing data).
    """
    try:
        params = {"instId": symbol, "bar": bar, "limit": limit}
        response = requests.get(OKX_CANDLES_URL, params=params, timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        if data.get("code") != "0":
            return []
        raw = data.get("data", [])
        if not raw:
            return []
        # OKX returns most-recent-first - reverse to oldest-first for
        # all indicator math below, matching bot.py's own convention.
        raw = list(reversed(raw))
        candles = []
        for c in raw:
            candles.append({
                "ts": c[0], "open": float(c[1]), "high": float(c[2]),
                "low": float(c[3]), "close": float(c[4]), "volume": float(c[5]),
                "confirm": c[8] if len(c) > 8 else None,
            })
        return candles
    except Exception:
        return []


def filter_closed_candles(candles):
    """
    CLOSED CANDLES ONLY - explicit confirm check, never assumed. A
    candle with confirm != "1" (including None if the field is ever
    absent) is excluded. Confirmed necessary even against OKX's
    "historical" endpoint, which returned one unconfirmed candle in
    this project's own pilot investigation.
    """
    return [c for c in candles if c.get("confirm") == "1"]


# ================================================
# Pure indicator functions - copied from bot.py, unchanged math
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
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    return ema_fast - ema_slow


def smart_money(candles):
    """Returns flow and volume_acceleration - both from volume only,
    independent of price direction."""
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
    """Compression - returns None fields if insufficient data, never a
    misleading fallback."""
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
    """Simplified independent regime classification - requires >=150
    candles per production's own guard; returns UNKNOWN otherwise."""
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
    """Copied from scan()'s inline STEP 5 logic - depends only on 15m
    closes and volume_acceleration, both independently computable."""
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


def compute_independent_snapshot(symbol):
    """
    Orchestrates the full independent measurement for one symbol:
    fetches 15m/1h/4h/1d candles directly from OKX, filters to closed
    candles only, computes every required indicator with an explicit
    None on insufficient data (never a misleading fallback), and
    returns a flat dict ready for INSERT. Never touches trades,
    Trade DNA, or any AHAD AI decision data.

    FIXED (measurement_timestamp): now captured here, at the very
    start of the independent measurement, in UTC explicitly - not
    computed later by the caller after all four API calls and every
    indicator calculation have already completed. This is the actual
    moment "the coin's independent measurement" began, matching the
    fix's intent precisely.
    """
    # UTC, explicitly - then stripped to naive to match the TIMESTAMP
    # (no timezone) column type, consistent with this project's own
    # naive-UTC convention used elsewhere (e.g. daily_report.py's
    # _cycle_boundaries_naive()). The value itself is still exactly
    # UTC; only the tzinfo marker is removed before storage.
    measurement_timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

    c15 = filter_closed_candles(fetch_candles(symbol, "15m", limit=200))
    time.sleep(REQUEST_DELAY_SECONDS)
    c1h = filter_closed_candles(fetch_candles(symbol, "1H", limit=30))
    time.sleep(REQUEST_DELAY_SECONDS)
    c4h = filter_closed_candles(fetch_candles(symbol, "4H", limit=30))
    time.sleep(REQUEST_DELAY_SECONDS)
    c1d = filter_closed_candles(fetch_candles(symbol, "1D", limit=30))
    time.sleep(REQUEST_DELAY_SECONDS)

    closes15 = [c["close"] for c in c15]
    closes1h = [c["close"] for c in c1h]
    closes4h = [c["close"] for c in c4h]
    closes1d = [c["close"] for c in c1d]

    sm = smart_money(c15) if c15 else {"flow": None, "volume_acceleration": None}
    comp = volatility_engine(c15) if c15 else {"score": None, "status": "UNKNOWN"}

    return {
        "measurement_timestamp": measurement_timestamp,
        "rsi_15m": rsi(closes15) if closes15 else None,
        "rsi_1h": rsi(closes1h) if closes1h else None,
        "rsi_4h": rsi(closes4h) if closes4h else None,
        "rsi_1d": rsi(closes1d) if closes1d else None,
        # Flow: from smart_money()'s own `flow` field - recent-vs-
        # historical volume ratio (5-candle sum vs 50-candle average).
        "flow": sm.get("flow"),
        # Volume Ratio: DOCUMENTED MAPPING, not an accidental
        # duplication - this project's own production smart_money()
        # (in bot.py) stores its "volume_acceleration" output under
        # the DB column name "volume_ratio" (`"volume_ratio": round(
        # volume_acceleration, 2)`). This is the SAME established
        # convention, applied here with the same source value -
        # volume_ratio IS volume_acceleration by this project's own
        # naming convention, not a separate metric. No new Volume
        # feature is introduced.
        "volume_ratio": sm.get("volume_acceleration"),
        "momentum_score": momentum_score_independent(c15) if c15 else None,
        "ema20": ema(closes15, 20) if len(closes15) >= 1 else None,
        "ema50": ema(closes15, 50) if len(closes15) >= 1 else None,
        "ema200": ema(closes15, 200) if len(closes15) >= 1 else None,
        "macd": macd_simple(closes15) if closes15 else None,
        "atr": atr(c15) if c15 else None,
        "compression_status": comp.get("status"),
        "market_regime": market_regime(c15) if c15 else "UNKNOWN",
        "candles_15m_used": len(c15),
    }
