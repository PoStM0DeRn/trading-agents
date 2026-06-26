"""Комплексные методы технического анализа: Ichimoku, Fibonacci, ADX."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


def _get_dataframe(ticker: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    """Получить DataFrame с историческими данными (через fallback market_data)."""
    from tools.market_data import get_historical_data
    candles = get_historical_data(ticker, period, "1d")
    if not candles:
        return None
    df = pd.DataFrame(candles)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# === 1. Ichimoku Cloud ===


def get_ichimoku(ticker: str, period: str = "6mo") -> dict:
    """Облако Ишимоку: Tenkan, Kijun, Senkou A/B, Chikou."""
    df = _get_dataframe(ticker, period)
    if df is None or len(df) < 52:
        return {"error": "Not enough data for Ichimoku (need 52+ candles)"}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)

    current_price = float(close.iloc[-1])
    cloud_top = max(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))
    cloud_bottom = min(float(senkou_a.iloc[-1]), float(senkou_b.iloc[-1]))

    if current_price > cloud_top:
        trend = "bullish"
    elif current_price < cloud_bottom:
        trend = "bearish"
    else:
        trend = "neutral"

    tk_cross = "bullish" if float(tenkan.iloc[-1]) > float(kijun.iloc[-1]) else "bearish"

    # Chikou vs price (26 bars ago)
    chikou_price_comparison = "above" if float(chikou.iloc[-1]) > float(close.iloc[-27]) else "below"

    # Cloud twist (Senkou A crossing Senkou B)
    cloud_twist = "none"
    if len(senkou_a.dropna()) >= 2 and len(senkou_b.dropna()) >= 2:
        sa_prev = float(senkou_a.dropna().iloc[-2])
        sb_prev = float(senkou_b.dropna().iloc[-2])
        sa_curr = float(senkou_a.dropna().iloc[-1])
        sb_curr = float(senkou_b.dropna().iloc[-1])
        if sa_prev <= sb_prev and sa_curr > sb_curr:
            cloud_twist = "bullish"
        elif sa_prev >= sb_prev and sa_curr < sb_curr:
            cloud_twist = "bearish"

    # Cloud color (green if Senkou A > Senkou B)
    cloud_color = "bullish" if float(senkou_a.iloc[-1]) > float(senkou_b.iloc[-1]) else "bearish"

    return {
        "tenkan": round(float(tenkan.iloc[-1]), 2),
        "kijun": round(float(kijun.iloc[-1]), 2),
        "senkou_a": round(float(senkou_a.iloc[-1]), 2),
        "senkou_b": round(float(senkou_b.iloc[-1]), 2),
        "chikou": round(float(chikou.iloc[-1]), 2),
        "cloud_top": round(cloud_top, 2),
        "cloud_bottom": round(cloud_bottom, 2),
        "trend": trend,
        "tk_cross": tk_cross,
        "chikou_vs_price": chikou_price_comparison,
        "cloud_twist": cloud_twist,
        "cloud_color": cloud_color,
        "price_vs_cloud": "above" if current_price > cloud_top else
                          "below" if current_price < cloud_bottom else "inside",
    }


# === 2. Fibonacci Retracement ===


def _find_swing_high_low(df: pd.DataFrame, lookback: int = 20) -> tuple[float, float, str]:
    """Находит последний swing high и swing low (fractal method).

    Swing high: бар, high которого выше high двух баров слева и двух справа.
    Swing low: бар, low которого ниже low двух баров слева и двух справа.
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(2, min(n - 2, lookback + 2) if lookback else n - 2):
        # Swing high
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append((i, highs[i]))
        # Swing low
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append((i, lows[i]))

    # Берём последний значимый swing high и swing low
    if not swing_highs:
        # Fallback: highest high за период
        start_idx = max(0, n - lookback - 2) if lookback else 0
        swing_high_val = float(highs[start_idx:].max())
    else:
        # Ближайший к текущему
        swing_high_val = swing_highs[-1][1]

    if not swing_lows:
        start_idx = max(0, n - lookback - 2) if lookback else 0
        swing_low_val = float(lows[start_idx:].min())
    else:
        swing_low_val = swing_lows[-1][1]

    # Определяем направление (upswing или downswing)
    direction = "uptrend" if swing_high_val > swing_low_val else "downtrend"

    return float(swing_high_val), float(swing_low_val), direction


def get_fibonacci_levels(ticker: str, period: str = "3mo") -> dict:
    """Уровни Фибоначчи от последних swing high/low (fractal method)."""
    df = _get_dataframe(ticker, period)
    if df is None or len(df) < 20:
        return {"error": "Not enough data for Fibonacci"}

    current_price = float(df["close"].iloc[-1])

    # Находим swing high/low
    swing_high, swing_low, direction = _find_swing_high_low(df)

    diff = swing_high - swing_low

    # Extension levels
    levels = {
        "0.0": swing_high,
        "23.6": swing_high - 0.236 * diff,
        "38.2": swing_high - 0.382 * diff,
        "50.0": swing_high - 0.5 * diff,
        "61.8": swing_high - 0.618 * diff,
        "78.6": swing_high - 0.786 * diff,
        "100.0": swing_low,
        "127.2": swing_low - 0.272 * diff,
        "161.8": swing_low - 0.618 * diff,
    }

    closest = min(levels.items(), key=lambda x: abs(x[1] - current_price))

    # Определяем, какие уровни были протестированы (price within 1% of level)
    tested_levels = []
    for name, price in levels.items():
        if abs(current_price - price) / price * 100 < 1.0:
            tested_levels.append(name)

    if current_price > levels["38.2"]:
        trend = "bullish"
    elif current_price < levels["61.8"]:
        trend = "bearish"
    else:
        trend = "neutral"

    return {
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "direction": direction,
        "levels": {k: round(v, 2) for k, v in levels.items()},
        "current_price": round(current_price, 2),
        "closest_level": closest[0],
        "closest_level_price": round(closest[1], 2),
        "tested_levels": tested_levels,
        "trend": trend,
    }


# === 3. ADX ===


def get_adx(ticker: str, period: str = "3mo", window: int = 14) -> dict:
    """ADX: сила тренда и направление (+DI, -DI)."""
    df = _get_dataframe(ticker, period)
    if df is None or len(df) < window * 2:
        return {"error": "Not enough data for ADX"}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr = tr.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / window, min_periods=window, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / window, min_periods=window, adjust=False).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.inf))
    adx = dx.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    current_adx = float(adx.iloc[-1])
    current_plus = float(plus_di.iloc[-1])
    current_minus = float(minus_di.iloc[-1])

    # ADX momentum (rising or falling)
    adx_rising = adx.iloc[-1] > adx.iloc[-3] if len(adx) >= 3 else False

    trend_strength = "strong" if current_adx > 25 else "weak"
    trend_direction = "bullish" if current_plus > current_minus else "bearish"

    return {
        "adx": round(current_adx, 2),
        "plus_di": round(current_plus, 2),
        "minus_di": round(current_minus, 2),
        "trend_strength": trend_strength,
        "trend_direction": trend_direction,
        "adx_rising": adx_rising,
        "signal": "trade" if current_adx > 25 else "no_trade",
    }


# === 4. Сводный анализ ===


def get_advanced_snapshot(ticker: str, period: str = "3mo") -> dict:
    """Полный снимок комплексных индикаторов."""
    results = {}
    for name, fn in [
        ("ichimoku", get_ichimoku),
        ("fibonacci", get_fibonacci_levels),
        ("adx", get_adx),
    ]:
        try:
            results[name] = fn(ticker, period)
        except Exception as e:
            logger.warning(f"Advanced analysis {name} failed for {ticker}: {e}")
            results[name] = {"error": str(e)}
    return results
