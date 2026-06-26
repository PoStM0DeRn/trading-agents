"""Trailing Stop — автоматическое перемещение стоп-лосса за ценой."""

import logging

logger = logging.getLogger(__name__)


def calculate_trailing_stop(
    entry_price: float,
    current_price: float,
    side: str = "LONG",
    trailing_percent: float = 2.0,
    current_stop: float = None,
) -> dict:
    """Рассчитать новый уровень trailing stop.

    Args:
        entry_price: Цена входа
        current_price: Текущая цена
        side: LONG или SHORT
        trailing_percent: Процент трейлинга
        current_stop: Текущий стоп-лосс

    Returns:
        dict с new_stop и action
    """
    if current_stop is None:
        current_stop = entry_price

    if side == "LONG":
        # Для LONG: стоп поднимается за растущей ценой
        new_stop_from_price = current_price * (1 - trailing_percent / 100)

        if new_stop_from_price > current_stop:
            return {
                "action": "move_stop_up",
                "new_stop": round(new_stop_from_price, 2),
                "old_stop": current_stop,
                "current_price": current_price,
                "locked_profit": round(current_price - entry_price, 2),
                "locked_profit_percent": round((current_price - entry_price) / entry_price * 100, 2),
            }
        return {
            "action": "no_change",
            "current_stop": current_stop,
            "current_price": current_price,
        }

    elif side == "SHORT":
        # Для SHORT: стоп опускается за падающей ценой
        new_stop_from_price = current_price * (1 + trailing_percent / 100)

        if new_stop_from_price < current_stop:
            return {
                "action": "move_stop_down",
                "new_stop": round(new_stop_from_price, 2),
                "old_stop": current_stop,
                "current_price": current_price,
                "locked_profit": round(entry_price - current_price, 2),
                "locked_profit_percent": round((entry_price - current_price) / entry_price * 100, 2),
            }
        return {
            "action": "no_change",
            "current_stop": current_stop,
            "current_price": current_price,
        }

    return {"action": "unknown_side", "side": side}


def check_trailing_stops(positions: list, current_prices: dict, config: dict = None) -> list:
    """Проверить все позиции и обновить trailing stops.

    Args:
        positions: Список позиций
        current_prices: Словарь {ticker: current_price}
        config: Конфигурация с trailing_percent

    Returns:
        Список обновлений стопов
    """
    if not config:
        config = {}

    trailing_percent = config.get("trading", {}).get("trailing_stop_percent", 2.0)
    updates = []

    for pos in positions:
        ticker = pos.get("ticker")
        side = pos.get("side", "LONG")
        entry_price = pos.get("entry_price", 0)
        current_stop = pos.get("stop_loss", entry_price)
        current_price = current_prices.get(ticker)

        if current_price is None or current_price <= 0:
            continue

        result = calculate_trailing_stop(
            entry_price=entry_price,
            current_price=current_price,
            side=side,
            trailing_percent=trailing_percent,
            current_stop=current_stop,
        )

        if result["action"] in ("move_stop_up", "move_stop_down"):
            updates.append({
                "ticker": ticker,
                "trade_id": pos.get("trade_id"),
                "old_stop": current_stop,
                "new_stop": result["new_stop"],
                "current_price": current_price,
                "locked_profit": result["locked_profit"],
                "locked_profit_percent": result["locked_profit_percent"],
            })

    return updates
