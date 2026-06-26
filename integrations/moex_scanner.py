"""MOEX Scanner — получение полного листинга акций Мосбиржи через T-Invest API."""

import logging
from datetime import datetime, timezone
from typing import Optional

from tinkoff.invest import Client
from tinkoff.invest.schemas import InstrumentStatus, InstrumentType

logger = logging.getLogger(__name__)

# Кэш листинга (обновляется раз в сессию)
_listing_cache: dict = {}
_cache_timestamp: Optional[datetime] = None
_CACHE_TTL_SECONDS = 3600  # 1 час


def get_all_moex_shares(
    token: str,
    sectors: list[str] = None,
    min_price_rub: float = 0,
    max_price_rub: float = 0,
    only_tradable: bool = True,
) -> list[dict]:
    """Получить все акции MOEX (TQBR класс) с фильтрацией.

    Возвращает список словарей:
    [
        {
            "ticker": "SBER",
            "figi": "BBG004730N88",
            "name": "Сбербанк",
            "lot": 10,
            "currency": "rub",
            "sector": "finance",
            "min_price_increment": 0.01,
            "d_long": true,
            "d_short": true,
        },
        ...
    ]
    """
    global _listing_cache, _cache_timestamp

    # Проверяем кэш
    if _listing_cache and _cache_timestamp:
        elapsed = (datetime.now(timezone.utc) - _cache_timestamp).total_seconds()
        if elapsed < _CACHE_TTL_SECONDS:
            logger.debug(f"Using cached MOEX listing ({len(_listing_cache)} shares, age {elapsed:.0f}s)")
            return _apply_filters(_listing_cache, sectors, min_price_rub, max_price_rub, only_tradable)

    logger.info("Fetching MOEX listing from T-Invest API...")

    try:
        with Client(token=token) as client:
            instruments = client.instruments

            # Запрашиваем акции MOEX (TQBR — основной режим торгов)
            response = instruments.shares(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
            )

            shares = []
            for instrument in response.instruments:
                # Фильтруем только TQBR ( Мосбиржа )
                if instrument.class_code != "TQBR":
                    continue

                # Определяем сектор
                sector = _map_exchange_to_sector(instrument.exchange)

                share = {
                    "ticker": instrument.ticker,
                    "figi": instrument.figi,
                    "name": instrument.name,
                    "lot": instrument.lot,
                    "currency": str(instrument.currency).lower() if instrument.currency else "rub",
                    "sector": sector,
                    "min_price_increment": (
                        instrument.min_price_increment.units + instrument.min_price_increment.nano / 1e9
                        if instrument.min_price_increment else 0.01
                    ),
                    "d_long": getattr(instrument, 'd_long', False),
                    "d_short": getattr(instrument, 'd_short', False),
                    "isin": getattr(instrument, 'isin', ''),
                    "focus": getattr(instrument, 'focus', ''),
                    "country_of_risk": getattr(instrument, 'country_of_risk', ''),
                    "trading_status": getattr(instrument, 'trading_status', ''),
                }
                shares.append(share)

            _listing_cache = shares
            _cache_timestamp = datetime.now(timezone.utc)

            logger.info(f"Fetched {len(shares)} MOEX TQBR shares")
            return _apply_filters(shares, sectors, min_price_rub, max_price_rub, only_tradable)

    except Exception as e:
        logger.error(f"Failed to fetch MOEX listing: {e}")
        # Возвращаем кэш если есть
        if _listing_cache:
            logger.warning("Using stale cache")
            return _apply_filters(_listing_cache, sectors, min_price_rub, max_price_rub, only_tradable)
        return []


def get_shares_count(token: str) -> int:
    """Получить количество доступных акций MOEX."""
    shares = get_all_moex_shares(token, only_tradable=True)
    return len(shares)


def get_share_info(token: str, ticker: str) -> Optional[dict]:
    """Получить информацию об одной акции."""
    shares = get_all_moex_shares(token, only_tradable=False)
    for s in shares:
        if s["ticker"] == ticker.upper():
            return s
    return None


def _apply_filters(
    shares: list[dict],
    sectors: list[str] = None,
    min_price_rub: float = 0,
    max_price_rub: float = 0,
    only_tradable: bool = True,
) -> list[dict]:
    """Применить фильтры к списку акций."""
    result = shares

    # Примечание: d_long/d_short отсутствуют в T-Invest API для большинства инструментов
    # Фильтрация по tradable не используется, так как все TQBR акции доступны для торгов

    if sectors:
        sectors_lower = [s.lower() for s in sectors]
        result = [s for s in result if s.get("sector", "").lower() in sectors_lower]

    return result


def _map_exchange_to_sector(exchange) -> str:
    """Маппинг биржи/сектора из T-Invest API на нашу систему секторов.

    Примечание: поле exchange в T-Invest API содержит технические значения
    (moex_morning_weekend, moex_mrng_evng_e_wknd_dlr и т.д.),
    поэтому используем дефолтное значение 'other'.
    Сектор определяется по тикеру в ticker_scanner.py.
    """
    return "other"


def clear_cache():
    """Очистить кэш листинга."""
    global _listing_cache, _cache_timestamp
    _listing_cache = {}
    _cache_timestamp = None
    logger.info("MOEX listing cache cleared")
