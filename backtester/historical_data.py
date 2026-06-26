import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data" / "backtest_cache"


def _cache_path(ticker: str, interval: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{ticker}_{interval}.json"


def fetch_candles(client, ticker: str, period: str, interval: str) -> list[dict]:
    cached = load_cached(ticker, interval, period)
    if cached is not None:
        logger.info(f"Loaded {len(cached)} cached candles for {ticker}")
        return cached

    logger.info(f"Fetching candles for {ticker} ({period}, {interval})...")
    candles = client.get_historical_data(ticker, period=period, interval=interval)
    logger.info(f"Fetched {len(candles)} candles for {ticker}")

    save_cache(ticker, interval, period, candles)
    return candles


def fetch_all(client, tickers: list[str], period: str, interval: str) -> dict[str, list[dict]]:
    result = {}
    for ticker in tickers:
        try:
            result[ticker] = fetch_candles(client, ticker, period, interval)
        except Exception as e:
            logger.error(f"Failed to fetch candles for {ticker}: {e}")
            result[ticker] = []
    return result


def load_cached(ticker: str, interval: str, period: str) -> list[dict] | None:
    path = _cache_path(ticker, interval)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("period") != period:
            return None

        cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        if age_hours > 24:
            return None

        return data.get("candles", [])
    except Exception as e:
        logger.warning(f"Failed to read cache for {ticker}: {e}")
        return None


def save_cache(ticker: str, interval: str, period: str, candles: list[dict]):
    path = _cache_path(ticker, interval)
    data = {
        "ticker": ticker,
        "interval": interval,
        "period": period,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "count": len(candles),
        "candles": candles,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Cached {len(candles)} candles for {ticker}")


def get_candle_at(candles: list[dict], index: int) -> dict | None:
    if 0 <= index < len(candles):
        return candles[index]
    return None


def get_closes(candles: list[dict]) -> list[float]:
    return [c["close"] for c in candles]


def get_price_at(candles: list[dict], index: int) -> float:
    candle = get_candle_at(candles, index)
    if candle:
        return candle["close"]
    return 0.0
