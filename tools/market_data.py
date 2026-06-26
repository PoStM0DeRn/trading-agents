"""Инструменты для получения рыночных данных."""

import logging

import numpy as np
import pandas as pd

from tools.retry import retry

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


def _ensure_client() -> bool:
    """Убедиться, что клиент подключён. Возвращает True если OK."""
    if _client is None:
        return False
    try:
        _client.ensure_connected()
        return True
    except Exception:
        return False


def get_current_quote(ticker: str) -> dict:
    """Возвращает текущую котировку: {bid, ask, last, spread, timestamp}."""
    if not _ensure_client():
        return {"ticker": ticker, "last": 0, "bid": 0, "ask": 0, "error": "client_not_connected"}
    try:
        return _client.get_quote(ticker)
    except Exception as e:
        logger.warning(f"T-Invest quote failed for {ticker}: {e}")
        return {"ticker": ticker, "last": 0, "bid": 0, "ask": 0, "error": str(e)}


def get_historical_data(
    ticker: str, period: str = "1mo", interval: str = "1d"
) -> list[dict]:
    """Возвращает список свечей за период."""
    if not _ensure_client():
        return []
    try:
        return _client.get_historical_data(ticker, period, interval)
    except Exception as e:
        logger.warning(f"T-Invest historical data failed for {ticker}: {e}")
        return []


def get_fundamentals(ticker: str) -> dict:
    """Возвращает фундаментальные показатели."""
    if not _ensure_client():
        return {"ticker": ticker, "error": "client_not_connected"}
    try:
        return _client.get_fundamentals(ticker)
    except Exception as e:
        logger.warning(f"Failed to get fundamentals for {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}


@retry(max_retries=2, base_delay=0.5, exceptions=(Exception,))
def get_technical_indicators(
    ticker: str, indicators: list[str], period: str = "3mo"
) -> dict:
    """Вычисляет технические индикаторы по историческим данным."""
    candles = get_historical_data(ticker, period, "1d")
    if not candles:
        return {"error": "No historical data available"}

    df = pd.DataFrame(candles)
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(int)

    result = {}

    for ind in indicators:
        ind_upper = ind.upper()
        if ind_upper == "RSI":
            result["RSI"] = _calc_rsi(df["close"], 14)
        elif ind_upper == "RSI_DIVERGENCE":
            result["RSI_DIVERGENCE"] = _calc_rsi_divergence(df)
        elif ind_upper == "MACD":
            macd_data = _calc_macd_full(df["close"])
            result["MACD"] = macd_data
        elif ind_upper.startswith("SMA_"):
            window = int(ind_upper.split("_")[1])
            result[ind_upper] = _calc_sma(df["close"], window)
        elif ind_upper == "BB":
            bb_data = _calc_bollinger_full(df["close"], 20)
            result["BB"] = bb_data
        elif ind_upper == "ATR":
            result["ATR"] = _calc_atr(df, 14)
        elif ind_upper == "VWAP":
            result["VWAP"] = _calc_vwap_intraday(df)

    return result


@retry(max_retries=2, base_delay=0.5, exceptions=(Exception,))
def get_support_resistance_levels(ticker: str, period: str = "3mo") -> dict:
    """Возвращает ключевые уровни support и resistance (multi-level с кластеризацией).

    Использует volume-weighted approach: уровни с наибольшим объёмом
    считаются более сильными. Возвращает список зон (clusters).
    """
    candles = get_historical_data(ticker, period, "1d")
    if not candles:
        return {"error": "No data"}

    df = pd.DataFrame(candles)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float) if "volume" in df.columns else pd.Series([1.0] * len(df))

    recent = df.tail(60)
    current_price = float(df["close"].iloc[-1])

    # Находим локальные экстремумы
    highs = []
    lows = []
    for i in range(2, len(recent) - 2):
        if recent["high"].iloc[i] > recent["high"].iloc[i-1] and \
           recent["high"].iloc[i] > recent["high"].iloc[i-2] and \
           recent["high"].iloc[i] > recent["high"].iloc[i+1] and \
           recent["high"].iloc[i] > recent["high"].iloc[i+2]:
            vol = recent["volume"].iloc[i]
            highs.append((float(recent["high"].iloc[i]), vol))
        if recent["low"].iloc[i] < recent["low"].iloc[i-1] and \
           recent["low"].iloc[i] < recent["low"].iloc[i-2] and \
           recent["low"].iloc[i] < recent["low"].iloc[i+1] and \
           recent["low"].iloc[i] < recent["low"].iloc[i+2]:
            vol = recent["volume"].iloc[i]
            lows.append((float(recent["low"].iloc[i]), vol))

    # Кластеризация уровней (group nearby levels)
    resistance_zones = _cluster_levels([p for p, _ in highs], [v for _, v in highs], current_price)
    support_zones = _cluster_levels([p for p, _ in lows], [v for _, v in lows], current_price)

    # Ближайшие уровни
    nearest_support = support_zones[0]["price"] if support_zones else float(recent["low"].nsmallest(3).mean())
    nearest_resistance = resistance_zones[0]["price"] if resistance_zones else float(recent["high"].nlargest(3).mean())

    return {
        "support_zones": support_zones[:3],
        "resistance_zones": resistance_zones[:3],
        "support": round(nearest_support, 2),
        "resistance": round(nearest_resistance, 2),
        "current_price": round(current_price, 2),
        "distance_to_support_pct": round(
            (current_price - nearest_support) / current_price * 100, 2
        ),
        "distance_to_resistance_pct": round(
            (nearest_resistance - current_price) / current_price * 100, 2
        ),
    }


def _cluster_levels(prices: list[float], volumes: list[float], current_price: float, threshold_pct: float = 1.5) -> list[dict]:
    """Кластеризует близкие уровни в зоны."""
    if not prices:
        return []

    # Сортируем по цене
    sorted_data = sorted(zip(prices, volumes), key=lambda x: x[0])

    clusters = []
    current_cluster_prices = [sorted_data[0][0]]
    current_cluster_volumes = [sorted_data[0][1]]

    for i in range(1, len(sorted_data)):
        price, vol = sorted_data[i]
        prev_price = current_cluster_prices[-1]
        pct_diff = abs(price - prev_price) / prev_price * 100

        if pct_diff <= threshold_pct:
            current_cluster_prices.append(price)
            current_cluster_volumes.append(vol)
        else:
            # Закрываем кластер
            avg_price = np.average(current_cluster_prices, weights=current_cluster_volumes)
            total_volume = sum(current_cluster_volumes)
            clusters.append({
                "price": round(float(avg_price), 2),
                "touches": len(current_cluster_prices),
                "volume": int(total_volume),
                "distance_pct": round(abs(avg_price - current_price) / current_price * 100, 2),
            })
            current_cluster_prices = [price]
            current_cluster_volumes = [vol]

    # Последний кластер
    avg_price = np.average(current_cluster_prices, weights=current_cluster_volumes)
    total_volume = sum(current_cluster_volumes)
    clusters.append({
        "price": round(float(avg_price), 2),
        "touches": len(current_cluster_prices),
        "volume": int(total_volume),
        "distance_pct": round(abs(avg_price - current_price) / current_price * 100, 2),
    })

    # Сортируем по расстоянию от текущей цены
    clusters.sort(key=lambda x: x["distance_pct"])
    return clusters


@retry(max_retries=2, base_delay=0.5, exceptions=(Exception,))
def get_volatility(ticker: str, period: str = "1mo") -> float:
    """Историческая волатильность в % за период."""
    candles = get_historical_data(ticker, period, "1d")
    if len(candles) < 2:
        return 0.0

    closes = [float(c["close"]) for c in candles]
    returns = np.diff(np.log(closes))
    vol = float(np.std(returns) * np.sqrt(252) * 100)
    return round(vol, 2)


@retry(max_retries=2, base_delay=0.5, exceptions=(Exception,))
def get_correlation(ticker1: str, ticker2: str, period: str = "3mo") -> float:
    """Коэффициент корреляции Пирсона по log returns (не по ценам)."""
    candles1 = get_historical_data(ticker1, period, "1d")
    candles2 = get_historical_data(ticker2, period, "1d")

    if not candles1 or not candles2:
        return 0.0

    df1 = pd.DataFrame(candles1)
    df2 = pd.DataFrame(candles2)

    # Выравниваем по времени
    df1["time"] = pd.to_datetime(df1["time"])
    df2["time"] = pd.to_datetime(df2["time"])
    merged = pd.merge(
        df1[["time", "close"]],
        df2[["time", "close"]],
        on="time",
        suffixes=("_1", "_2"),
    )

    if len(merged) < 10:
        return 0.0

    # Корреляция по log returns, а не по ценам
    log_returns_1 = np.log(merged["close_1"].astype(float) / merged["close_1"].astype(float).shift(1))
    log_returns_2 = np.log(merged["close_2"].astype(float) / merged["close_2"].astype(float).shift(1))

    # Убираем NaN
    valid = log_returns_1.notna() & log_returns_2.notna()
    if valid.sum() < 10:
        return 0.0

    corr = log_returns_1[valid].corr(log_returns_2[valid])
    return round(float(corr), 4)


# --- Внутренние функции расчёта индикаторов ---


def _calc_rsi(prices: pd.Series, window: int = 14) -> float:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.inf)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def _calc_rsi_divergence(df: pd.DataFrame, rsi_period: int = 14, lookback: int = 14) -> dict:
    """Обнаружение дивергенции RSI.

    Бычья дивергенция: цена делает новый минимум, а RSI — нет (потенциальный разворот вверх).
    Медвежья дивергенция: цена делает новый максимум, а RSI — нет (потенциальный разворот вниз).
    """
    if len(df) < rsi_period + lookback:
        return {"divergence": "none", "type": None}

    # RSI series
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.inf)
    rsi = 100 - (100 / (1 + rs))

    # Ищем минимумы/максимумы за lookback периодов
    recent_close = df["close"].tail(lookback)
    recent_rsi = rsi.tail(lookback)

    if len(recent_close) < lookback or recent_rsi.isna().all():
        return {"divergence": "none", "type": None}

    # Бычья дивергенция: цена падает, RSI растёт
    price_making_lower_low = df["close"].iloc[-1] < df["close"].tail(lookback).min() * 1.01
    rsi_making_higher_low = rsi.iloc[-1] > rsi.tail(lookback).min() * 1.05

    # Медвежья дивергенция: цена растёт, RSI падает
    price_making_higher_high = df["close"].iloc[-1] > df["close"].tail(lookback).max() * 0.99
    rsi_making_lower_high = rsi.iloc[-1] < rsi.tail(lookback).max() * 0.95

    if price_making_lower_low and rsi_making_higher_low:
        return {
            "divergence": "bullish",
            "type": "bullish",
            "price_low": round(float(df["close"].iloc[-1]), 2),
            "rsi_value": round(float(rsi.iloc[-1]), 2),
        }
    elif price_making_higher_high and rsi_making_lower_high:
        return {
            "divergence": "bearish",
            "type": "bearish",
            "price_high": round(float(df["close"].iloc[-1]), 2),
            "rsi_value": round(float(rsi.iloc[-1]), 2),
        }

    return {"divergence": "none", "type": None}


def _calc_macd_full(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict:
    """MACD с анализом convergence/divergence гистограммы."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    # Анализ convergence/divergence гистограммы
    hist_series = histogram.tail(6)
    hist_direction = "none"
    if len(hist_series) >= 3:
        hist_values = hist_series.values
        # Convergence: гистограмма приближается к нулю
        if abs(hist_values[-1]) < abs(hist_values[-3]) and abs(hist_values[-1]) < abs(hist_values[-2]):
            hist_direction = "convergence"
        # Divergence: гистограмма удаляется от нуля
        elif abs(hist_values[-1]) > abs(hist_values[-3]) and abs(hist_values[-1]) > abs(hist_values[-2]):
            hist_direction = "divergence"

    # Zero-line crossover
    zero_cross = "none"
    if len(macd_line) >= 2:
        if macd_line.iloc[-1] > 0 and macd_line.iloc[-2] <= 0:
            zero_cross = "bullish"
        elif macd_line.iloc[-1] < 0 and macd_line.iloc[-2] >= 0:
            zero_cross = "bearish"

    return {
        "macd": round(float(macd_line.iloc[-1]), 4),
        "signal": round(float(signal_line.iloc[-1]), 4),
        "histogram": round(float(histogram.iloc[-1]), 4),
        "trend": "bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "bearish",
        "histogram_direction": hist_direction,
        "zero_line_cross": zero_cross,
    }


def _calc_sma(prices: pd.Series, window: int) -> float:
    sma = prices.rolling(window=window, min_periods=window).mean()
    return round(float(sma.iloc[-1]), 2)


def _calc_bollinger_full(
    prices: pd.Series, window: int = 20, num_std: float = 2.0
) -> dict:
    """Bollinger Bands с %B, Bandwidth и Squeeze detection."""
    sma = prices.rolling(window=window, min_periods=window).mean()
    std = prices.rolling(window=window, min_periods=window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std

    current_price = float(prices.iloc[-1])
    upper_val = float(upper.iloc[-1])
    lower_val = float(lower.iloc[-1])
    middle_val = float(sma.iloc[-1])

    # %B: позиция цены относительно полос (0 = lower, 1 = upper)
    band_width = upper_val - lower_val
    pct_b = (current_price - lower_val) / band_width if band_width > 0 else 0.5

    # Bandwidth: ширина полос относительно middle
    bandwidth = (upper_val - lower_val) / middle_val if middle_val > 0 else 0

    # Squeeze detection: bandwidth ниже порога (исторически узкие полосы)
    bandwidth_series = (upper - lower) / sma.replace(0, np.nan)
    bandwidth_percentile = bandwidth_series.rank(pct=True).iloc[-1] if not bandwidth_series.isna().all() else 0.5
    squeeze = bandwidth_percentile < 0.2  # Ниже 20-го перцентиля

    return {
        "upper": round(upper_val, 2),
        "middle": round(middle_val, 2),
        "lower": round(lower_val, 2),
        "pct_b": round(float(pct_b), 4),
        "bandwidth": round(float(bandwidth), 4),
        "squeeze": squeeze,
    }


def _calc_atr(df: pd.DataFrame, window: int = 14) -> float:
    """ATR через Wilder's EMA (согласовано с ADX)."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    # Wilder's EMA (alpha = 1/window)
    atr = tr.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    return round(float(atr.iloc[-1]), 2)


def _calc_vwap_intraday(df: pd.DataFrame) -> dict:
    """VWAP с intraday reset и стандартными отклонениями."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3

    # Кумулятивный VWAP (для дневных данных — приближение)
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap = cum_tp_vol / cum_vol

    # Стандартное отклонение VWAP
    vwap_diff = typical_price - vwap
    vwap_std = ((vwap_diff ** 2).cumsum() / cum_vol).apply(np.sqrt)

    current_vwap = float(vwap.iloc[-1])
    current_std = float(vwap_std.iloc[-1])
    current_price = float(df["close"].iloc[-1])

    return {
        "vwap": round(current_vwap, 2),
        "vwap_upper_1": round(current_vwap + current_std, 2),
        "vwap_lower_1": round(current_vwap - current_std, 2),
        "vwap_upper_2": round(current_vwap + 2 * current_std, 2),
        "vwap_lower_2": round(current_vwap - 2 * current_std, 2),
        "price_vs_vwap": "above" if current_price > current_vwap else "below",
    }
