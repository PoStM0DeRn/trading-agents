"""Fundamentals — фундаментальные данные MOEX акций."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_fundamentals_cache: dict = {}
_cache_timestamps: dict = {}
_CACHE_TTL = 86400

MOEX_TICKERS = {
    "SBER": "SBER", "GAZP": "GAZP", "LKOH": "LKOH", "GMKN": "GMKN",
    "YDEX": "YDEX", "VTBR": "VTBR", "ROSN": "ROSN", "NVTK": "NVTK",
    "SNGS": "SNGS", "TATN": "TATN", "ALRS": "ALRS", "PLZL": "PLZL",
    "PHOR": "PHOR", "AFLT": "AFLT",
}

# Sector classification for relative valuation
SECTORS = {
    "financial": ["SBER", "VTBR", "ALRS", "TCSG", "CBOM", "AKRN", "BANE", "BANEP"],
    "oil_gas": ["GAZP", "LKOH", "ROSN", "NVTK", "SNGS", "TATN", "SNGSP"],
    "metals": ["GMKN", "NLMK", "CHMF", "AKZN", "ALRS"],
    "tech": ["YDEX", "OZON", "PLAT", "KLVZ"],
    "retail": ["MGNT", "FIVE", "FIXP", "OKEY"],
    "telecom": ["MTSS", "RTKM", "RTKMP"],
}

SECTOR_AVG = {
    "financial": {"pe": 5.5, "pb": 0.8, "dy": 5.5},
    "oil_gas": {"pe": 6.5, "pb": 1.1, "dy": 5.0},
    "metals": {"pe": 7.0, "pb": 1.0, "dy": 4.0},
    "tech": {"pe": 18.0, "pb": 3.0, "dy": 0.5},
    "retail": {"pe": 20.0, "pb": 2.5, "dy": 1.0},
    "telecom": {"pe": 10.0, "pb": 1.5, "dy": 6.0},
}


def _get_sector(ticker: str) -> Optional[str]:
    """Определить сектор по тикеру."""
    for sector, tickers in SECTORS.items():
        if ticker.upper() in tickers:
            return sector
    return None


def get_fundamentals(ticker: str) -> dict:
    """Получение фундаментальных данных MOEX акции."""
    ticker = ticker.upper()

    if ticker in _fundamentals_cache:
        cached_time = _cache_timestamps.get(ticker, 0)
        if time.time() - cached_time < _CACHE_TTL:
            return _fundamentals_cache[ticker]

    result = {
        "ticker": ticker,
        "pe_ratio": None,
        "pb_ratio": None,
        "dividend_yield": None,
        "market_cap": None,
        "lot_size": 1,
        "sector": _get_sector(ticker),
        "source": "stub",
    }

    _apply_known_fundamentals(result, ticker)

    result["sector_relative"] = _sector_relative_valuation(result, ticker)

    _fundamentals_cache[ticker] = result
    _cache_timestamps[ticker] = time.time()
    return result


def _apply_known_fundamentals(result: dict, ticker: str):
    known = {
        "SBER":  {"pe_ratio": 5.8, "pb_ratio": 1.2, "dividend_yield": 6.5, "market_cap": 5_800_000_000_000},
        "GAZP":  {"pe_ratio": 4.2, "pb_ratio": 0.8, "dividend_yield": 8.2, "market_cap": 3_200_000_000_000},
        "LKOH":  {"pe_ratio": 7.1, "pb_ratio": 1.5, "dividend_yield": 4.8, "market_cap": 5_100_000_000_000},
        "GMKN":  {"pe_ratio": 8.5, "pb_ratio": 1.1, "dividend_yield": 3.2, "market_cap": 2_100_000_000_000},
        "YDEX":  {"pe_ratio": 22.0, "pb_ratio": 3.5, "dividend_yield": 0.0, "market_cap": 1_800_000_000_000},
        "VTBR":  {"pe_ratio": 4.5, "pb_ratio": 0.4, "dividend_yield": 5.0, "market_cap": 1_100_000_000_000},
        "ROSN":  {"pe_ratio": 6.2, "pb_ratio": 0.9, "dividend_yield": 5.5, "market_cap": 3_500_000_000_000},
        "NVTK":  {"pe_ratio": 8.0, "pb_ratio": 1.3, "dividend_yield": 2.5, "market_cap": 3_100_000_000_000},
        "SNGS":  {"pe_ratio": 5.0, "pb_ratio": 0.6, "dividend_yield": 7.0, "market_cap": 800_000_000_000},
        "TATN":  {"pe_ratio": 5.5, "pb_ratio": 0.7, "dividend_yield": 6.0, "market_cap": 1_500_000_000_000},
        "ALRS":  {"pe_ratio": 6.0, "pb_ratio": 0.9, "dividend_yield": 5.0, "market_cap": 600_000_000_000},
        "PLZL":  {"pe_ratio": 4.5, "pb_ratio": 1.8, "dividend_yield": 12.0, "market_cap": 400_000_000_000},
    }
    data = known.get(ticker)
    if data:
        for k, v in data.items():
            if result.get(k) is None:
                result[k] = v
        result["source"] = "known_fundamentals"
    else:
        result["pe_ratio"] = 10.0
        result["pb_ratio"] = 1.0
        result["dividend_yield"] = 3.0
        result["source"] = "default_fundamentals"


def _sector_relative_valuation(result: dict, ticker: str) -> dict:
    """Compare stock's valuation to sector averages.

    Returns relative discount/premium for each metric.
    """
    sector = result.get("sector")
    if not sector:
        return {"available": False, "reason": "no_sector"}

    avg = SECTOR_AVG.get(sector)
    if not avg:
        return {"available": False, "reason": "no_sector_avg"}

    pe = result.get("pe_ratio")
    pb = result.get("pb_ratio")
    dy = result.get("dividend_yield")

    report = {"sector": sector, "sector_avg": avg, "metrics": {}}

    if pe is not None and avg["pe"] and avg["pe"] > 0:
        pe_ratio = pe / avg["pe"]
        if pe_ratio < 0.7:
            signal = "cheap_vs_sector"
        elif pe_ratio < 0.9:
            signal = "slightly_cheap"
        elif pe_ratio > 1.3:
            signal = "expensive_vs_sector"
        elif pe_ratio > 1.1:
            signal = "slightly_expensive"
        else:
            signal = "fair_value"
        report["metrics"]["pe"] = {
            "stock": pe, "sector_avg": avg["pe"], "ratio": round(pe_ratio, 2), "signal": signal
        }

    if pb is not None and avg["pb"] and avg["pb"] > 0:
        pb_ratio = pb / avg["pb"]
        if pb_ratio < 0.7:
            signal = "cheap_vs_sector"
        elif pb_ratio < 0.9:
            signal = "slightly_cheap"
        elif pb_ratio > 1.3:
            signal = "expensive_vs_sector"
        elif pb_ratio > 1.1:
            signal = "slightly_expensive"
        else:
            signal = "fair_value"
        report["metrics"]["pb"] = {
            "stock": pb, "sector_avg": avg["pb"], "ratio": round(pb_ratio, 2), "signal": signal
        }

    if dy is not None and avg["dy"] is not None and avg["dy"] > 0:
        dy_ratio = dy / avg["dy"]
        if dy_ratio > 1.3:
            signal = "high_yield"
        elif dy_ratio > 1.1:
            signal = "slightly_high_yield"
        elif dy_ratio < 0.5:
            signal = "low_yield"
        elif dy_ratio < 0.8:
            signal = "slightly_low_yield"
        else:
            signal = "fair_yield"
        report["metrics"]["dy"] = {
            "stock": dy, "sector_avg": avg["dy"], "ratio": round(dy_ratio, 2), "signal": signal
        }

    # Overall sector valuation score
    signals = [m["signal"] for m in report["metrics"].values()]
    cheap_count = sum(1 for s in signals if "cheap" in s or s == "high_yield")
    expensive_count = sum(1 for s in signals if "expensive" in s or s == "low_yield")

    if cheap_count > expensive_count:
        report["overall"] = "undervalued_vs_sector"
    elif expensive_count > cheap_count:
        report["overall"] = "overvalued_vs_sector"
    else:
        report["overall"] = "fair_value"

    report["available"] = True
    return report


def get_valuation_signal(pe_ratio: float, pb_ratio: float, dividend_yield: float) -> dict:
    score = 0
    details = []

    if pe_ratio is not None:
        if pe_ratio < 5:
            score += 2
            details.append(f"P/E очень низкий ({pe_ratio:.1f}) — дешево")
        elif pe_ratio < 8:
            score += 1
            details.append(f"P/E низкий ({pe_ratio:.1f})")
        elif pe_ratio > 25:
            score -= 2
            details.append(f"P/E очень высокий ({pe_ratio:.1f}) — дорого")
        elif pe_ratio > 15:
            score -= 1
            details.append(f"P/E высокий ({pe_ratio:.1f})")

    if pb_ratio is not None:
        if pb_ratio < 0.5:
            score += 1
            details.append(f"P/B < 0.5 ({pb_ratio:.1f}) — глубокий дисконт")
        elif pb_ratio > 3:
            score -= 1
            details.append(f"P/B > 3 ({pb_ratio:.1f}) — дорого")

    if dividend_yield is not None:
        if dividend_yield > 7:
            score += 1
            details.append(f"Высокая дивидендная доходность ({dividend_yield:.1f}%)")
        elif dividend_yield > 5:
            score += 1
            details.append(f"Хорошая дивидендная доходность ({dividend_yield:.1f}%)")

    signal = "undervalued" if score > 0 else "overvalued" if score < 0 else "fair_value"

    return {"score": score, "signal": signal, "details": details}
