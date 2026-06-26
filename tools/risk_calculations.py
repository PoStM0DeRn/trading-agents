"""Инструменты для расчёта позиций и рисков (с плечом)."""

import logging

logger = logging.getLogger(__name__)


def calculate_position_size_long(
    capital: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
) -> int:
    """Расчёт размера позиции для LONG.

    Формула: (capital * risk_percent / 100) / |entry - stop_loss|
    Возвращает количество акций (целое, округление вниз).
    """
    if entry_price <= 0 or stop_loss_price <= 0 or capital <= 0:
        raise ValueError("All prices and capital must be positive")
    if stop_loss_price >= entry_price:
        raise ValueError("For LONG: stop_loss must be below entry_price")

    risk_amount = capital * (risk_percent / 100)
    risk_per_share = entry_price - stop_loss_price
    quantity = int(risk_amount / risk_per_share)

    if quantity <= 0:
        raise ValueError("Position size too small for given risk parameters")

    return quantity


def calculate_position_size_short(
    capital: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
    borrow_rate_annual: float = 0.0,
    expected_hold_days: int = 1,
) -> int:
    """Расчёт размера позиции для SHORT.

    С учётом стоимости займа акций.
    stop_loss_price ДОЛЖЕН быть выше entry_price для шорта.
    """
    if entry_price <= 0 or stop_loss_price <= 0 or capital <= 0:
        raise ValueError("All prices and capital must be positive")
    if stop_loss_price <= entry_price:
        raise ValueError("For SHORT: stop_loss must be above entry_price")

    # Стоимость займа за период
    borrow_cost_per_share = entry_price * (borrow_rate_annual / 100) * (expected_hold_days / 365)

    risk_amount = capital * (risk_percent / 100)
    risk_per_share = (stop_loss_price - entry_price) + borrow_cost_per_share

    if risk_per_share <= 0:
        raise ValueError("Effective risk per share is non-positive")

    quantity = int(risk_amount / risk_per_share)

    if quantity <= 0:
        raise ValueError("Position size too small for given risk parameters")

    return quantity


def calculate_total_commission(
    ticker: str,
    quantity: int,
    price: float,
    side: str,
    execution_style: str = "limit",
) -> dict:
    """Расчёт комиссии за одну сделку.

    Тариф: 0.04% от суммы, без минимума.
    """
    trade_value = quantity * price
    commission = trade_value * 0.0004

    commission_percent = (commission / trade_value * 100) if trade_value > 0 else 0

    return {
        "commission_amount": round(commission, 2),
        "commission_percent": round(commission_percent, 4),
        "effective_cost": round(trade_value + commission, 2),
        "trade_value": round(trade_value, 2),
        "currency": "RUB",
    }


def calculate_cycle_commission(
    ticker: str,
    quantity: int,
    entry_price: float,
    exit_price: float,
    side: str,
) -> dict:
    """Суммарная комиссия за цикл (открытие + закрытие).

    side: LONG_OPEN или SHORT_OPEN — определяет направление сделки.
    """
    # Комиссия за открытие
    if side == "LONG_OPEN":
        open_commission = calculate_total_commission(ticker, quantity, entry_price, "BUY")
    else:
        open_commission = calculate_total_commission(ticker, quantity, entry_price, "SELL")

    # Комиссия за закрытие (противоположная сторона)
    if side == "LONG_OPEN":
        close_commission = calculate_total_commission(ticker, quantity, exit_price, "SELL")
    else:
        close_commission = calculate_total_commission(ticker, quantity, exit_price, "BUY")

    total_commission = open_commission["commission_amount"] + close_commission["commission_amount"]
    total_value = open_commission["trade_value"] + close_commission["trade_value"]

    return {
        "open_commission": open_commission["commission_amount"],
        "close_commission": close_commission["commission_amount"],
        "total_commission": round(total_commission, 2),
        "total_commission_percent": round(
            (total_commission / total_value * 100) if total_value > 0 else 0, 4
        ),
        "cycle_cost": round(
            open_commission["effective_cost"]
            + close_commission["effective_cost"]
            - open_commission["trade_value"]
            - close_commission["trade_value"],
            2,
        ),
    }


def calculate_portfolio_risk(positions: list[dict]) -> dict:
    """Анализ рисков портфеля.

    Принимает список позиций: [{ticker, quantity, entry_price, stop_loss, current_price}]
    """
    if not positions:
        return {
            "total_exposure": 0,
            "var_95": 0,
            "max_drawdown": 0,
            "sector_exposure": {},
            "positions_count": 0,
        }

    total_value = sum(
        p.get("quantity", 0) * p.get("current_price", p.get("entry_price", 0))
        for p in positions
    )

    # Экспозиция по позициям
    exposures = []
    for p in positions:
        pos_value = p.get("quantity", 0) * p.get("current_price", p.get("entry_price", 0))
        exposures.append({
            "ticker": p.get("ticker"),
            "value": pos_value,
            "weight": round(pos_value / total_value * 100, 2) if total_value > 0 else 0,
            "unrealized_pnl": p.get("quantity", 0)
            * (
                p.get("current_price", p.get("entry_price", 0))
                - p.get("entry_price", 0)
            ),
        })

    # VaR (упрощённый): максимальный потенциальный убыток по стопам
    total_risk = 0
    for p in positions:
        entry = p.get("entry_price", 0)
        stop = p.get("stop_loss", entry)
        qty = p.get("quantity", 0)
        if entry > 0 and stop > 0:
            risk = abs(entry - stop) * qty
            total_risk += risk

    # Максимальная просадка (по текущим убыткам)
    max_drawdown = sum(
        min(0, e["unrealized_pnl"]) for e in exposures
    )

    return {
        "total_value": round(total_value, 2),
        "total_risk": round(total_risk, 2),
        "max_drawdown": round(max_drawdown, 2),
        "positions_count": len(positions),
        "positions": exposures,
        "risk_per_trade_avg": round(
            total_risk / len(positions) / total_value * 100, 2
        ) if positions and total_value > 0 else 0,
    }


def calculate_position_size_leveraged(
    capital: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
    leverage: float = 3.0,
    side: str = "LONG",
) -> dict:
    """Расчёт размера позиции с плечом × leverage.

    capital — собственный капитал (не заёмные).
    leverage — множитель (3.0 = ×3, т.е. на 100₽ своих ставим 300₽).
    risk_percent — риск в % от СОБСТВЕННОГО капитала (loss = risk_amount × leverage).

    Returns:
        {
            "quantity": int,
            "total_cost": float,        # полная стоимость позиции
            "own_required": float,      # сколько своих средств
            "borrowed": float,          # заёмные средства
            "risk_amount": float,       # максимальный убыток (включая leverage)
            "risk_per_share": float,
        }
    """
    if entry_price <= 0 or stop_loss_price <= 0 or capital <= 0 or leverage < 1:
        raise ValueError("Invalid parameters for leveraged position")
    if side == "LONG" and stop_loss_price >= entry_price:
        raise ValueError("For LONG: stop_loss must be below entry_price")
    if side == "SHORT" and stop_loss_price <= entry_price:
        raise ValueError("For SHORT: stop_loss must be above entry_price")

    risk_per_share = abs(entry_price - stop_loss_price)
    # Максимальный убыток = risk_percent% от capital × leverage (плечо усиливает и убыток)
    risk_amount = capital * (risk_percent / 100) * leverage
    quantity = int(risk_amount / risk_per_share)

    if quantity <= 0:
        raise ValueError("Position size too small for given risk/leverage parameters")

    total_cost = quantity * entry_price
    own_required = total_cost / leverage
    borrowed = total_cost - own_required

    return {
        "quantity": quantity,
        "total_cost": round(total_cost, 2),
        "own_required": round(own_required, 2),
        "borrowed": round(borrowed, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
    }


def check_volume_limit(ticker: str, quantity: int) -> dict:
    """Проверяет, что объём не превышает допустимую долю дневного оборота.

    Максимум 5% от среднего дневного объёма.
    """
    daily_volume_estimate = 500_000
    max_allowed = int(daily_volume_estimate * 0.05)
    return {
        "allowed": quantity <= max_allowed,
        "requested_quantity": quantity,
        "max_allowed": max_allowed,
        "daily_volume_estimate": daily_volume_estimate,
        "source": "estimate",
    }


