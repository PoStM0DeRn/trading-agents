"""Microstructure analysis — order book imbalance, volume pressure, OBV, volume profile."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


def _ensure_client() -> bool:
    if _client is None:
        return False
    try:
        _client.ensure_connected()
        return True
    except Exception:
        return False


def get_order_book_imbalance(ticker: str, depth: int = 20) -> dict:
    """Analyze order book depth — bid vs ask pressure."""
    if not _ensure_client():
        return {"error": "client_not_connected", "imbalance": 0, "signal": "neutral"}
    try:

        figi = _client._resolve_figi(ticker)
        book = _client._market_data.get_order_book(figi=figi, depth=depth)

        bid_volumes = [b.quantity for b in book.bids]
        ask_volumes = [a.quantity for a in book.asks]

        total_bid = sum(bid_volumes)
        total_ask = sum(ask_volumes)
        total = total_bid + total_ask

        imbalance = 0.0
        if total > 0:
            imbalance = round((total_bid - total_ask) / total, 4)

        return {
            "imbalance": imbalance,
            "bid_volume": total_bid,
            "ask_volume": total_ask,
            "bid_levels": len(bid_volumes),
            "ask_levels": len(ask_volumes),
            "large_bid": max(bid_volumes) if bid_volumes else 0,
            "large_ask": max(ask_volumes) if ask_volumes else 0,
            "signal": "bullish" if imbalance > 0.15 else "bearish" if imbalance < -0.15 else "neutral",
        }
    except Exception as e:
        logger.warning(f"Order book imbalance failed for {ticker}: {e}")
        return {"error": str(e), "imbalance": 0, "signal": "neutral"}


def get_volume_pressure(ticker: str, period: str = "1mo") -> dict:
    """Analyze volume patterns — above/below average, trend."""
    from tools.market_data import get_historical_data
    try:
        candles = get_historical_data(ticker, period, "1d")
    except Exception as e:
        logger.warning(f"Volume pressure failed for {ticker}: {e}")
        return {"error": str(e)}
    if len(candles) < 5:
        return {"error": "Not enough data"}

    volumes = [c["volume"] for c in candles]
    avg_vol = np.mean(volumes)
    current_vol = volumes[-1]
    ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 0

    mid = len(volumes) // 2
    first_half = np.mean(volumes[:mid]) if mid > 0 else 0
    second_half = np.mean(volumes[mid:]) if mid > 0 else 0
    if second_half > first_half * 1.1:
        trend = "increasing"
    elif second_half < first_half * 0.9:
        trend = "decreasing"
    else:
        trend = "stable"

    high_vol_days = sum(1 for v in volumes if v > avg_vol * 1.5)

    return {
        "avg_volume": int(avg_vol),
        "current_volume": int(current_vol),
        "volume_ratio": ratio,
        "volume_trend": trend,
        "high_volume_days": high_vol_days,
        "signal": "bullish" if ratio > 1.5 and trend == "increasing" else
                  "bearish" if ratio > 1.5 and trend == "decreasing" else "neutral",
    }


def get_obv(ticker: str, period: str = "3mo") -> dict:
    """On-Balance Volume — confirms trend with volume."""
    from tools.market_data import get_historical_data
    candles = get_historical_data(ticker, period, "1d")
    if len(candles) < 10:
        return {"error": "Not enough data"}

    closes = np.array([float(c["close"]) for c in candles])
    volumes = np.array([c["volume"] for c in candles])

    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    obv_series = pd.Series(obv)
    obv_sma_short = obv_series.rolling(5).mean().iloc[-1]
    obv_sma_long = obv_series.rolling(20).mean().iloc[-1] if len(obv) >= 20 else obv_sma_short

    obv_trend = "bullish" if obv_sma_short > obv_sma_long else "bearish"

    price_change = (closes[-1] - closes[-5]) / closes[-5] if closes[-5] != 0 else 0
    obv_change = (obv[-1] - obv[-5]) / abs(obv[-5]) if obv[-5] != 0 else 0
    divergence = (price_change > 0.01 and obv_change < -0.01) or (price_change < -0.01 and obv_change > 0.01)

    return {
        "obv": round(float(obv[-1]), 0),
        "obv_trend": obv_trend,
        "obv_divergence": divergence,
        "signal": "bearish_divergence" if divergence and price_change > 0 else
                  "bullish_divergence" if divergence and price_change < 0 else obv_trend,
    }


def get_volume_profile(ticker: str, period: str = "3mo", bins: int = 20) -> dict:
    """Volume Profile using H-L range per bar (not just close).

    Each candle contributes volume proportional to its price range to the bins it touches.
    This gives a more accurate picture of where trading actually happened.
    """
    from tools.market_data import get_historical_data
    candles = get_historical_data(ticker, period, "1d")
    if len(candles) < 10:
        return {"error": "Not enough data"}

    df = pd.DataFrame(candles)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(int)

    price_min = df["low"].min()
    price_max = df["high"].max()
    if price_min == price_max:
        return {"poc": price_min, "value_area_high": price_max, "value_area_low": price_min, "profile": []}

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    volume_at_level = np.zeros(bins)

    for _, row in df.iterrows():
        bar_low = row["low"]
        bar_high = row["high"]
        bar_vol = row["volume"]

        # Find which bins this bar's H-L range touches
        for b in range(bins):
            level_low = bin_edges[b]
            level_high = bin_edges[b + 1]
            # Check if bar range overlaps this bin
            if bar_low <= level_high and bar_high >= level_low:
                # Proportion of volume in this bin based on overlap
                overlap_low = max(bar_low, level_low)
                overlap_high = min(bar_high, level_high)
                range_width = bar_high - bar_low
                if range_width > 0:
                    proportion = (overlap_high - overlap_low) / range_width
                    volume_at_level[b] += bar_vol * proportion

    poc_idx = int(np.argmax(volume_at_level))
    poc = round(float(bin_centers[poc_idx]), 2)

    # Value Area: 70% of total volume around POC
    total_vol = volume_at_level.sum()
    target_vol = total_vol * 0.7
    accumulated = volume_at_level[poc_idx]
    va_low_idx = poc_idx
    va_high_idx = poc_idx

    while accumulated < target_vol and (va_low_idx > 0 or va_high_idx < bins - 1):
        down_vol = volume_at_level[va_low_idx - 1] if va_low_idx > 0 else 0
        up_vol = volume_at_level[va_high_idx + 1] if va_high_idx < bins - 1 else 0
        if down_vol >= up_vol and va_low_idx > 0:
            va_low_idx -= 1
            accumulated += volume_at_level[va_low_idx]
        elif va_high_idx < bins - 1:
            va_high_idx += 1
            accumulated += volume_at_level[va_high_idx]
        else:
            break

    # Top 5 levels
    top_indices = np.argsort(volume_at_level)[-5:][::-1]
    profile = [{"price": round(float(bin_centers[i]), 2), "volume": int(volume_at_level[i])} for i in top_indices]

    # Buy/sell pressure estimate: volume above/below current close
    current_close = df["close"].iloc[-1]
    vol_above = sum(volume_at_level[i] for i in range(bins) if bin_centers[i] > current_close)
    vol_below = sum(volume_at_level[i] for i in range(bins) if bin_centers[i] < current_close)
    vol_ratio = vol_above / vol_below if vol_below > 0 else float("inf")

    return {
        "poc": poc,
        "value_area_high": round(float(bin_centers[va_high_idx]), 2),
        "value_area_low": round(float(bin_centers[va_low_idx]), 2),
        "profile": profile,
        "current_price": round(float(current_close), 2),
        "vol_above_poc": int(vol_above),
        "vol_below_poc": int(vol_below),
        "vol_ratio_above_below": round(vol_ratio, 2),
        "poc_distance_pct": round((current_close - poc) / poc * 100, 2),
        "signal": "resistance" if current_close > poc and vol_ratio > 1.5 else
                  "support" if current_close < poc and vol_ratio < 0.67 else "balanced",
    }
