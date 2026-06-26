"""Slippage Model — модель проскальзывания для backtest."""

import logging

logger = logging.getLogger(__name__)


def calculate_slippage(
    price: float,
    quantity: int,
    side: str = "BUY",
    slippage_type: str = "fixed",
    slippage_percent: float = 0.05,
    slippage_abs: float = 0.0,
    volume_impact: float = 0.0001,
) -> dict:
    """Рассчитать проскальзывание для сделки.

    Args:
        price: Цена инструмента
        quantity: Количество
        side: BUY или SELL
        slippage_type: fixed, percent, or impact
        slippage_percent: Процент проскальзывания (для percent типа)
        slippage_abs: Абсолютное проскальзывание (для fixed типа)
        volume_impact: Коэффициент влияния объёма (для impact типа)

    Returns:
        dict с adjusted_price и slippage_amount
    """
    if price <= 0:
        return {"adjusted_price": price, "slippage_amount": 0, "slippage_type": "none"}

    order_value = price * quantity

    if slippage_type == "fixed":
        slippage_amount = slippage_abs
    elif slippage_type == "percent":
        slippage_amount = price * slippage_percent / 100
    elif slippage_type == "impact":
        # Простая модель: проскальзывание зависит от объёма
        slippage_amount = price * volume_impact * (quantity / 100)
    else:
        slippage_amount = 0

    # Для BUY проскальзывание увеличивает цену
    # Для SELL проскальзывание уменьшает цену
    if side == "BUY":
        adjusted_price = price + slippage_amount
    else:
        adjusted_price = price - slippage_amount

    return {
        "adjusted_price": round(adjusted_price, 2),
        "slippage_amount": round(slippage_amount, 2),
        "slippage_type": slippage_type,
        "order_value_impact": round(slippage_amount * quantity, 2),
    }


def apply_slippage_to_execution(
    entry_price: float,
    quantity: int,
    side: str,
    config: dict = None,
) -> dict:
    """Применить проскальзывание к исполнению ордера.

    Args:
        entry_price: Цена входа
        quantity: Количество
        side: LONG_OPEN, SHORT_OPEN, LONG_CLOSE, SHORT_CLOSE
        config: Конфигурация с параметрами slippage

    Returns:
        dict с adjusted_price и slippage_info
    """
    if not config:
        config = {}

    slippage_config = config.get("backtest", {}).get("slippage", {})
    slippage_type = slippage_config.get("type", "percent")
    slippage_percent = slippage_config.get("percent", 0.05)
    slippage_abs = slippage_config.get("abs", 0.0)
    volume_impact = slippage_config.get("volume_impact", 0.0001)

    # Определяем сторону для проскальзывания
    if "OPEN" in side:
        exec_side = "BUY" if "LONG" in side else "SELL"
    else:
        exec_side = "SELL" if "LONG" in side else "BUY"

    result = calculate_slippage(
        price=entry_price,
        quantity=quantity,
        side=exec_side,
        slippage_type=slippage_type,
        slippage_percent=slippage_percent,
        slippage_abs=slippage_abs,
        volume_impact=volume_impact,
    )

    return {
        "original_price": entry_price,
        "adjusted_price": result["adjusted_price"],
        "slippage_amount": result["slippage_amount"],
        "slippage_type": result["slippage_type"],
        "order_value_impact": result["order_value_impact"],
    }
