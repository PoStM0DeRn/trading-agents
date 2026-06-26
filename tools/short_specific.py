"""Специализированные инструменты для шортов.

NOTE: Short trading на MOEX доступен для маржинальных инструментов.
Для включения установить allow_shorts=true в config/settings.yaml.
"""

import logging

logger = logging.getLogger(__name__)

_client = None
_config = None


def set_client(client):
    global _client
    _client = client


def set_config(config: dict):
    global _config
    _config = config


def _allow_shorts() -> bool:
    """Проверить, включены ли шорты в конфиге."""
    if _config:
        return _config.get("trading", {}).get("allow_shorts", False)
    return False


def get_short_interest(ticker: str) -> float:
    """Процент акций в свободном обращении, проданных в шорт.

    Для MOEX: данных FINRA/SEC нет, возвращаем 0.
    """
    return 0.0


def get_borrow_rate(ticker: str) -> float:
    """Годовая ставка за заём акций у брокера (в %).

    Для MOEX: ставка фиксированная ~20% (оценка T-Invest).
    """
    return 20.0


def check_short_availability(ticker: str) -> dict:
    """Проверка доступности бумаг для шорта.

    Если allow_shorts=true в конфиге — шорт доступен.
    """
    available = _allow_shorts()

    if available:
        return {
            "available": True,
            "max_quantity": 1000,
            "borrow_rate": get_borrow_rate(ticker),
            "short_interest": get_short_interest(ticker),
            "note": "Short trading enabled via config",
        }
    else:
        return {
            "available": False,
            "max_quantity": 0,
            "borrow_rate": 20.0,
            "short_interest": 0.0,
            "warning": "SHORT_TRADING_DISABLED",
            "note": "Short trading disabled. Enable via config: allow_shorts=true",
        }


def get_dividend_calendar(
    ticker: str, date_from: str = None, date_to: str = None
) -> list[dict]:
    """Ближайшие даты отсечек и размер дивидендов."""
    return [
        {
            "ticker": ticker,
            "ex_date": None,
            "pay_date": None,
            "dividend_per_share": 0.0,
            "note": "Dividend data not available",
        }
    ]
