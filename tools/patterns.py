"""Candlestick pattern recognition with trend context."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


def _prepare_df(ticker: str, period: str = "3mo") -> pd.DataFrame:
    from tools.market_data import get_historical_data
    candles = get_historical_data(ticker, period, "1d")
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype(int)
    df["body"] = df["close"] - df["open"]
    df["body_abs"] = df["body"].abs()
    df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["range"] = df["high"] - df["low"]
    return df


def _avg_body(df: pd.DataFrame, n: int = 10) -> float:
    if len(df) < n:
        n = len(df)
    return df["body_abs"].tail(n).mean()


def _detect_trend(df: pd.DataFrame, lookback: int = 20) -> str:
    """Определяет текущий тренд по SMA(20)."""
    if len(df) < lookback:
        return "neutral"
    sma = df["close"].rolling(lookback).mean()
    if df["close"].iloc[-1] > sma.iloc[-1]:
        return "bullish"
    elif df["close"].iloc[-1] < sma.iloc[-1]:
        return "bearish"
    return "neutral"


def _precompute_trends(df: pd.DataFrame, lookback: int = 20) -> list[str]:
    """Precompute trend for each bar position (vectorized, O(n) total)."""
    if len(df) < lookback:
        return ["neutral"] * len(df)
    sma = df["close"].rolling(lookback).mean()
    trends = []
    for i in range(len(df)):
        if i < lookback - 1:
            trends.append("neutral")
        elif df["close"].iloc[i] > sma.iloc[i]:
            trends.append("bullish")
        elif df["close"].iloc[i] < sma.iloc[i]:
            trends.append("bearish")
        else:
            trends.append("neutral")
    return trends


def detect_doji(df: pd.DataFrame, threshold: float = 0.1) -> list[int]:
    """Doji: body is very small relative to range."""
    _avg_body(df)
    indices = []
    for i in range(len(df)):
        row = df.iloc[i]
        if row["range"] > 0 and row["body_abs"] < row["range"] * threshold:
            indices.append(i)
    return indices


def detect_hammer(df: pd.DataFrame) -> list[int]:
    """Hammer: small body at top, long lower shadow (>= 2x body). Only valid in downtrend."""
    trends = _precompute_trends(df)
    indices = []
    for i in range(len(df)):
        row = df.iloc[i]
        if row["body_abs"] > 0 and row["lower_shadow"] >= row["body_abs"] * 2 and row["upper_shadow"] < row["body_abs"]:
            if i >= 2 and trends[i] == "bearish":
                indices.append(i)
            elif i < 2:
                indices.append(i)
    return indices


def detect_inverted_hammer(df: pd.DataFrame) -> list[int]:
    """Inverted Hammer: small body at bottom, long upper shadow. Only valid in downtrend."""
    trends = _precompute_trends(df)
    indices = []
    for i in range(len(df)):
        row = df.iloc[i]
        if row["body_abs"] > 0 and row["upper_shadow"] >= row["body_abs"] * 2 and row["lower_shadow"] < row["body_abs"]:
            if i >= 2 and trends[i] == "bearish":
                indices.append(i)
            elif i < 2:
                indices.append(i)
    return indices


def detect_bullish_engulfing(df: pd.DataFrame) -> list[int]:
    """Bullish Engulfing: bearish candle followed by larger bullish candle."""
    indices = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if prev["body"] < 0 and curr["body"] > 0:
            if curr["open"] <= prev["close"] and curr["close"] >= prev["open"]:
                indices.append(i)
    return indices


def detect_bearish_engulfing(df: pd.DataFrame) -> list[int]:
    """Bearish Engulfing: bullish candle followed by larger bearish candle."""
    indices = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if prev["body"] > 0 and curr["body"] < 0:
            if curr["open"] >= prev["close"] and curr["close"] <= prev["open"]:
                indices.append(i)
    return indices


def detect_shooting_star(df: pd.DataFrame) -> list[int]:
    """Shooting Star: small body at bottom, long upper shadow (>= 2x body). Only valid in uptrend."""
    trends = _precompute_trends(df)
    indices = []
    for i in range(len(df)):
        row = df.iloc[i]
        if row["body_abs"] > 0 and row["upper_shadow"] >= row["body_abs"] * 2 and row["lower_shadow"] < row["body_abs"]:
            if i >= 2 and trends[i] == "bullish":
                indices.append(i)
            elif i < 2:
                indices.append(i)
    return indices


def detect_three_white_soldiers(df: pd.DataFrame) -> list[int]:
    """Three White Soldiers: 3 consecutive bullish candles, each closing higher."""
    indices = []
    for i in range(2, len(df)):
        c1, c2, c3 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
        if c1["body"] > 0 and c2["body"] > 0 and c3["body"] > 0:
            if c2["close"] > c1["close"] and c3["close"] > c2["close"]:
                if c2["open"] > c1["open"] and c3["open"] > c2["open"]:
                    indices.append(i)
    return indices


def detect_three_black_crows(df: pd.DataFrame) -> list[int]:
    """Three Black Crows: 3 consecutive bearish candles, each closing lower."""
    indices = []
    for i in range(2, len(df)):
        c1, c2, c3 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
        if c1["body"] < 0 and c2["body"] < 0 and c3["body"] < 0:
            if c2["close"] < c1["close"] and c3["close"] < c2["close"]:
                if c2["open"] < c1["open"] and c3["open"] < c2["open"]:
                    indices.append(i)
    return indices


def detect_morning_star(df: pd.DataFrame) -> list[int]:
    """Morning Star: bearish candle, small body, bullish candle."""
    indices = []
    for i in range(2, len(df)):
        c1, c2, c3 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
        avg = _avg_body(df)
        if c1["body"] < 0 and c3["body"] > 0:
            if c2["body_abs"] < avg * 0.5:
                if c3["close"] > (c1["open"] + c1["close"]) / 2:
                    indices.append(i)
    return indices


def detect_evening_star(df: pd.DataFrame) -> list[int]:
    """Evening Star: bullish candle, small body, bearish candle."""
    indices = []
    for i in range(2, len(df)):
        c1, c2, c3 = df.iloc[i - 2], df.iloc[i - 1], df.iloc[i]
        avg = _avg_body(df)
        if c1["body"] > 0 and c3["body"] < 0:
            if c2["body_abs"] < avg * 0.5:
                if c3["close"] < (c1["open"] + c1["close"]) / 2:
                    indices.append(i)
    return indices


# === Новые паттерны ===


def detect_bullish_harami(df: pd.DataFrame) -> list[int]:
    """Bullish Harami: large bearish candle followed by smaller bullish candle inside its body."""
    indices = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if prev["body"] < 0 and curr["body"] > 0:
            if curr["open"] >= prev["close"] and curr["close"] <= prev["open"]:
                if curr["body_abs"] < prev["body_abs"] * 0.6:
                    indices.append(i)
    return indices


def detect_bearish_harami(df: pd.DataFrame) -> list[int]:
    """Bearish Harami: large bullish candle followed by smaller bearish candle inside its body."""
    indices = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if prev["body"] > 0 and curr["body"] < 0:
            if curr["open"] <= prev["close"] and curr["close"] >= prev["open"]:
                if curr["body_abs"] < prev["body_abs"] * 0.6:
                    indices.append(i)
    return indices


def detect_piercing_line(df: pd.DataFrame) -> list[int]:
    """Piercing Line: bearish candle followed by bullish candle that opens below low but closes above midpoint."""
    indices = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if prev["body"] < 0 and curr["body"] > 0:
            midpoint = (prev["open"] + prev["close"]) / 2
            if curr["open"] < prev["low"] and curr["close"] > midpoint and curr["close"] < prev["open"]:
                indices.append(i)
    return indices


def detect_dark_cloud_cover(df: pd.DataFrame) -> list[int]:
    """Dark Cloud Cover: bullish candle followed by bearish candle that opens above high but closes below midpoint."""
    indices = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if prev["body"] > 0 and curr["body"] < 0:
            midpoint = (prev["open"] + prev["close"]) / 2
            if curr["open"] > prev["high"] and curr["close"] < midpoint and curr["close"] > prev["open"]:
                indices.append(i)
    return indices


PATTERN_DETECTORS = {
    "doji": detect_doji,
    "hammer": detect_hammer,
    "inverted_hammer": detect_inverted_hammer,
    "bullish_engulfing": detect_bullish_engulfing,
    "bearish_engulfing": detect_bearish_engulfing,
    "shooting_star": detect_shooting_star,
    "three_white_soldiers": detect_three_white_soldiers,
    "three_black_crows": detect_three_black_crows,
    "morning_star": detect_morning_star,
    "evening_star": detect_evening_star,
    "bullish_harami": detect_bullish_harami,
    "bearish_harami": detect_bearish_harami,
    "piercing_line": detect_piercing_line,
    "dark_cloud_cover": detect_dark_cloud_cover,
}

BULLISH_PATTERNS = {
    "hammer", "inverted_hammer", "bullish_engulfing", "three_white_soldiers",
    "morning_star", "bullish_harami", "piercing_line",
}
BEARISH_PATTERNS = {
    "shooting_star", "bearish_engulfing", "three_black_crows", "evening_star",
    "bearish_harami", "dark_cloud_cover",
}

# Pattern reliability weights (higher = more reliable)
PATTERN_WEIGHTS = {
    "doji": 1,
    "hammer": 2,
    "inverted_hammer": 2,
    "bullish_engulfing": 3,
    "bearish_engulfing": 3,
    "shooting_star": 2,
    "three_white_soldiers": 3,
    "three_black_crows": 3,
    "morning_star": 3,
    "evening_star": 3,
    "bullish_harami": 2,
    "bearish_harami": 2,
    "piercing_line": 2,
    "dark_cloud_cover": 2,
}


def get_candlestick_patterns(ticker: str, period: str = "3mo") -> dict:
    """Detect all candlestick patterns and return summary with trend context."""
    df = _prepare_df(ticker, period)
    if df.empty:
        return {"error": "No data"}

    trend = _detect_trend(df)

    found_bullish = []
    found_bearish = []
    all_patterns = {}

    for name, detector in PATTERN_DETECTORS.items():
        indices = detector(df)
        # Only care about recent patterns (last 5 candles)
        recent = [i for i in indices if i >= len(df) - 5]
        if recent:
            weight = PATTERN_WEIGHTS.get(name, 1)
            all_patterns[name] = {
                "count_total": len(indices),
                "recent_count": len(recent),
                "last_index": recent[-1],
                "weight": weight,
                "reliability": "high" if weight >= 3 else "medium" if weight == 2 else "low",
            }
            if name in BULLISH_PATTERNS:
                found_bullish.append(name)
            elif name in BEARISH_PATTERNS:
                found_bearish.append(name)

    # Weighted signal
    bullish_score = sum(PATTERN_WEIGHTS.get(p, 1) for p in found_bullish)
    bearish_score = sum(PATTERN_WEIGHTS.get(p, 1) for p in found_bearish)

    if bullish_score > bearish_score:
        signal = "bullish"
    elif bearish_score > bullish_score:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "patterns": all_patterns,
        "bullish_patterns": found_bullish,
        "bearish_patterns": found_bearish,
        "bullish_score": bullish_score,
        "bearish_score": bearish_score,
        "signal": signal,
        "trend": trend,
        "pattern_reliability": "high" if any(p.get("weight", 1) >= 3 for p in all_patterns.values()) else "medium",
        "last_5_candles": df.tail(5)[["time", "open", "high", "low", "close", "volume"]].to_dict("records"),
    }
