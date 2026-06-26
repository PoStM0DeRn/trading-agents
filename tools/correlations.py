"""Cross-market correlations — Brent, USD/RUB, MOEX Index."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


# Known FIGIs for benchmarks (verified)
BENCHMARK_FIGI = {
    "USDRUB": "BBG0013HGFT4",  # USD/RUB on CETS
}

# Oil/gas sector tickers for implied oil correlation
OIL_GAS_SECTOR = {"GAZP", "LKOH", "ROSN", "NVTK", "SNGS", "SNGSP", "BANE", "BANEP"}


def _get_benchmark_candles(benchmark: str, period: str = "3mo") -> list[dict]:
    """Get candles for a benchmark instrument. Returns empty if unavailable."""
    logger.debug(f"Benchmark {benchmark} data not available via T-Invest")
    return []


def _calc_log_return_correlation(series1: pd.Series, series2: pd.Series) -> float:
    """Корреляция по log returns (правильный метод для финансовых рядов)."""
    log_ret1 = np.log(series1 / series1.shift(1))
    log_ret2 = np.log(series2 / series2.shift(1))
    valid = log_ret1.notna() & log_ret2.notna()
    if valid.sum() < 10:
        return 0.0
    return float(log_ret1[valid].corr(log_ret2[valid]))


def get_brent_correlation(ticker: str, period: str = "3mo") -> dict:
    """Estimate oil sensitivity.

    Since Brent futures are not available via T-Invest API, we use GAZP as an oil proxy.
    If the ticker IS GAZP/LKOH/ROSN/NVTK, we flag it as oil-sensitive by sector.
    """
    ticker_upper = ticker.upper()

    # Direct sector-based flag
    if ticker_upper in OIL_GAS_SECTOR:
        # Compare with GAZP as oil proxy
        if ticker_upper != "GAZP":
            try:
                from tools.correlations import get_sector_correlation
                corr_result = get_sector_correlation(ticker_upper, "GAZP", period)
                return {
                    "correlation": corr_result.get("correlation", 0),
                    "benchmark": "GAZP_proxy",
                    "data_points": corr_result.get("data_points", 0),
                    "signal": "oil_sensitive" if corr_result.get("correlation", 0) > 0.5 else "moderate_oil_link",
                }
            except Exception:
                pass

        return {
            "correlation": 0,
            "benchmark": "sector_flag",
            "signal": "oil_sensitive",
            "note": "Oil/gas sector ticker — correlation not available via API",
        }

    return {
        "correlation": 0,
        "benchmark": "N/A",
        "signal": "not_oil_sector",
        "note": "Brent not available via API; ticker is not in oil/gas sector",
    }


def get_usdrub_correlation(ticker: str, period: str = "3mo") -> dict:
    """Correlation of a ticker with USD/RUB using log returns."""
    from tools.market_data import get_historical_data
    stock_candles = get_historical_data(ticker, period, "1d")
    fx_candles = _get_benchmark_candles("USDRUB", period)

    if not stock_candles or not fx_candles:
        return {"correlation": 0, "benchmark": "USDRUB", "error": "No data"}

    df_stock = pd.DataFrame(stock_candles)[["time", "close"]].rename(columns={"close": "stock"})
    df_fx = pd.DataFrame(fx_candles)[["time", "close"]].rename(columns={"close": "usdrub"})

    df_stock["time"] = pd.to_datetime(df_stock["time"]).dt.date.astype(str)
    df_fx["time"] = pd.to_datetime(df_fx["time"]).dt.date.astype(str)

    merged = pd.merge(df_stock, df_fx, on="time")
    if len(merged) < 10:
        return {"correlation": 0, "benchmark": "USDRUB", "error": "Not enough overlap"}

    # Корреляция по log returns
    corr = _calc_log_return_correlation(
        merged["stock"].astype(float), merged["usdrub"].astype(float)
    )

    return {
        "correlation": round(corr, 4),
        "benchmark": "USDRUB",
        "data_points": len(merged),
        "signal": "usd_sensitive" if abs(corr) > 0.5 else "usd_neutral",
    }


def get_sector_correlation(ticker1: str, ticker2: str, period: str = "3mo") -> dict:
    """Direct correlation between two tickers using log returns."""
    from tools.market_data import get_historical_data
    candles1 = get_historical_data(ticker1, period, "1d")
    candles2 = get_historical_data(ticker2, period, "1d")

    if not candles1 or not candles2:
        return {"correlation": 0, "error": "No data"}

    df1 = pd.DataFrame(candles1)[["time", "close"]].rename(columns={"close": "p1"})
    df2 = pd.DataFrame(candles2)[["time", "close"]].rename(columns={"close": "p2"})

    df1["time"] = pd.to_datetime(df1["time"]).dt.date.astype(str)
    df2["time"] = pd.to_datetime(df2["time"]).dt.date.astype(str)

    merged = pd.merge(df1, df2, on="time")
    if len(merged) < 10:
        return {"correlation": 0, "error": "Not enough overlap"}

    # Корреляция по log returns
    corr = _calc_log_return_correlation(
        merged["p1"].astype(float), merged["p2"].astype(float)
    )

    return {
        "correlation": round(corr, 4),
        "ticker1": ticker1,
        "ticker2": ticker2,
        "data_points": len(merged),
    }


def get_market_context(ticker: str, period: str = "3mo") -> dict:
    """Full market context: correlations with oil, FX, and sector peers."""
    oil_corr = get_brent_correlation(ticker, period)
    fx_corr = get_usdrub_correlation(ticker, period)

    return {
        "ticker": ticker,
        "oil_correlation": oil_corr,
        "usd_correlation": fx_corr,
        "oil_sensitive": oil_corr.get("signal") == "oil_sensitive",
        "usd_sensitive": fx_corr.get("signal") == "usd_sensitive",
    }
