"""Virtual Portfolio — paper trading без реального исполнения (с плечом)."""

import logging
import sqlite3
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_conn():
    from tools.memory import get_raw_conn
    conn = get_raw_conn(check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_columns():
    """Добавить новые колонки если их нет (миграция)."""
    conn = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE virtual_account ADD COLUMN borrowed REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE virtual_positions ADD COLUMN leverage REAL DEFAULT 1.0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE virtual_positions ADD COLUMN borrowed REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def open_position(
    ticker: str,
    side: str,
    quantity: int,
    entry_price: float,
    stop_loss: float = 0,
    take_profit: float = 0,
    commission: float = 0,
    strategy: str = "",
    rationale: str = "",
    leverage: float = 1.0,
    trade_id: str = None,
) -> dict:
    """Открыть виртуальную позицию с плечом.

    Args:
        leverage: Множитель плеча (1.0 = без плеча, 3.0 = x3).
                  own_required = total_cost / leverage
                  borrowed = total_cost - own_required
        trade_id: Optional external trade_id (e.g. from proposal). If None, generates UUID.
    """
    _ensure_columns()
    trade_id = trade_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    total_cost = quantity * entry_price
    own_required = total_cost / leverage if leverage > 1 else total_cost
    borrowed = total_cost - own_required if leverage > 1 else 0
    total_with_commission = own_required + commission

    conn = _get_conn()
    cursor = conn.cursor()

    # Проверяем баланс
    cursor.execute("SELECT current_balance FROM virtual_account WHERE id = 1")
    row = cursor.fetchone()
    balance = row[0] if row else 0

    if total_with_commission > balance:
        conn.close()
        logger.warning(
            f"Insufficient balance: need {total_with_commission:.2f} "
            f"(own={own_required:.2f} + commission={commission:.2f}), "
            f"have {balance:.2f}"
        )
        return {"status": "rejected", "reason": "insufficient_balance"}

    # Списываем свои средства + комиссию
    new_balance = balance - total_with_commission
    new_borrowed = (cursor.execute("SELECT borrowed FROM virtual_account WHERE id = 1").fetchone()[0] or 0) + borrowed

    cursor.execute(
        "UPDATE virtual_account SET current_balance = ?, borrowed = ?, updated_at = ? WHERE id = 1",
        (new_balance, new_borrowed, now),
    )

    # Открываем позицию
    try:
        cursor.execute("""
            INSERT INTO virtual_positions
            (trade_id, ticker, side, quantity, entry_price, stop_loss, take_profit,
             status, opened_at, commission, strategy, rationale, leverage, borrowed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
        """, (trade_id, ticker, side, quantity, entry_price, stop_loss, take_profit,
              now, commission, strategy, rationale, leverage, borrowed))
    except sqlite3.IntegrityError:
        conn.commit()
        conn.close()
        logger.warning(f"Position already exists for trade_id={trade_id} — returning existing")
        return {"status": "already_open", "trade_id": trade_id}

    conn.commit()
    conn.close()

    logger.info(
        f"Virtual position opened: {side} {quantity} {ticker} @ {entry_price:.2f} "
        f"| leverage=x{leverage:.1f} | own={own_required:.2f} | borrowed={borrowed:.2f} "
        f"| commission={commission:.2f}"
    )
    return {
        "status": "filled",
        "trade_id": trade_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "entry_price": entry_price,
        "commission": commission,
        "leverage": leverage,
        "own_required": round(own_required, 2),
        "borrowed": round(borrowed, 2),
    }


def close_position(trade_id: str, close_price: float) -> dict:
    """Закрыть виртуальную позицию."""
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM virtual_positions WHERE trade_id = ? AND status = 'open'", (trade_id,))
    pos = cursor.fetchone()

    if not pos:
        conn.close()
        return {"status": "error", "reason": "position_not_found"}

    pos = dict(pos)
    quantity = pos["quantity"]
    entry_price = pos["entry_price"]
    side = pos["side"]
    pos["commission"]
    position_borrowed = pos.get("borrowed", 0) or 0

    # Рассчитываем P&L (на полную сумму, включая заёмные)
    if side == "LONG":
        pnl = (close_price - entry_price) * quantity
    else:
        pnl = (entry_price - close_price) * quantity

    # Комиссия закрытия — рассчитывается по close_price (0.04%)
    close_commission = quantity * close_price * 0.0004
    net_pnl = pnl - close_commission

    # Возвращаем на счёт
    cursor.execute("SELECT current_balance, borrowed FROM virtual_account WHERE id = 1")
    row = cursor.fetchone()
    balance = row[0]
    total_borrowed = row[1] or 0

    if side == "LONG":
        returned = quantity * close_price - position_borrowed
    else:
        own_required = quantity * entry_price - position_borrowed
        returned = own_required + (entry_price - close_price) * quantity

    new_balance = balance + returned - close_commission
    new_borrowed = max(0, total_borrowed - position_borrowed)

    cursor.execute(
        "UPDATE virtual_account SET current_balance = ?, borrowed = ?, updated_at = ? WHERE id = 1",
        (new_balance, new_borrowed, now),
    )

    # Закрываем позицию
    cursor.execute("""
        UPDATE virtual_positions
        SET status = 'closed', closed_at = ?, close_price = ?, pnl = ?, commission = commission + ?
        WHERE trade_id = ?
    """, (now, close_price, net_pnl, close_commission, trade_id))

    # Также записываем в trades для статистики
    cursor.execute("""
        INSERT OR REPLACE INTO trades
        (trade_id, ticker, action, quantity, entry_price, exit_price,
         stop_loss, take_profit, pnl, commission, strategy, rationale,
         opened_at, closed_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed')
    """, (
        trade_id, pos["ticker"], side, quantity, entry_price, close_price,
        pos["stop_loss"], pos["take_profit"], net_pnl, close_commission,
        pos["strategy"], pos["rationale"], pos["opened_at"], now,
    ))

    conn.commit()
    conn.close()

    logger.info(
        f"Virtual position closed: {trade_id} @ {close_price:.2f} "
        f"| P&L={net_pnl:.2f} | returned_borrowed={position_borrowed:.2f}"
    )
    return {
        "status": "closed",
        "trade_id": trade_id,
        "pnl": net_pnl,
        "close_price": close_price,
        "returned_borrowed": position_borrowed,
    }


def get_positions() -> list[dict]:
    """Получить все открытые виртуальные позиции."""
    _ensure_columns()
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM virtual_positions WHERE status = 'open' ORDER BY opened_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_closed_positions(limit: int = 50) -> list[dict]:
    """Получить закрытые позиции."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM virtual_positions WHERE status = 'closed' ORDER BY closed_at DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_balance() -> dict:
    """Получить текущий баланс виртуального счёта."""
    _ensure_columns()
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM virtual_account WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "initial_capital": 100000, "current_balance": 100000,
            "borrowed": 0, "positions_value": 0, "total_value": 100000,
        }

    row = dict(row)
    initial = row["initial_capital"]
    balance = row["current_balance"]
    borrowed = row.get("borrowed", 0) or 0

    positions = get_positions()
    positions_value = sum(p["quantity"] * p["entry_price"] for p in positions)

    return {
        "initial_capital": initial,
        "current_balance": balance,
        "borrowed": borrowed,
        "positions_value": positions_value,
        "total_value": balance + positions_value,
    }


def get_margin_level(current_prices: dict = None) -> dict:
    """Рассчитать текущий Margin Level.

    Returns:
        {
            "own_capital": float,      -- собственный капитал (balance + equity_in_positions + unrealized_pnl)
            "borrowed": float,         -- заёмные средства
            "total_equity": float,     -- total = own_capital (уже включает P&L)
            "margin_level": float,     -- margin_level % (total_equity / borrowed * 100)
            "margin_call": bool,       -- margin_level < 50%
            "liquidation": bool,       -- margin_level < 30%
            "leverage_used": float,    -- текущее плечо (total_position_value / own_capital)
        }
    """
    _ensure_columns()
    balance_info = get_balance()
    positions = get_positions()

    balance = balance_info["current_balance"]
    borrowed = balance_info["borrowed"]

    # Считаем unrealized P&L
    total_pnl = 0
    total_position_value = 0
    total_own_in_positions = 0

    for pos in positions:
        ticker = pos["ticker"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        side = pos["side"]
        pos_borrowed = pos.get("borrowed", 0) or 0

        current = entry
        if current_prices and ticker in current_prices:
            current = current_prices[ticker]

        if side == "LONG":
            pnl = (current - entry) * qty
            total_position_value += current * qty
        else:
            pnl = (entry - current) * qty
            total_position_value += current * qty

        total_pnl += pnl
        total_own_in_positions += (entry * qty - pos_borrowed)

    # own_capital = cash balance + equity in positions + unrealized P&L
    own_capital = balance + total_own_in_positions + total_pnl

    # Margin Level
    if borrowed > 0:
        margin_level = (own_capital / borrowed) * 100
    else:
        margin_level = float("inf")

    # Текущее плечо
    if own_capital > 0:
        leverage_used = total_position_value / own_capital
    else:
        leverage_used = 0

    return {
        "own_capital": round(own_capital, 2),
        "borrowed": round(borrowed, 2),
        "total_equity": round(own_capital, 2),
        "margin_level": round(margin_level, 2),
        "margin_call": margin_level < 50 and borrowed > 0,
        "liquidation": margin_level < 30 and borrowed > 0,
        "leverage_used": round(leverage_used, 2),
        "total_position_value": round(total_position_value, 2),
        "total_pnl": round(total_pnl, 2),
    }


def get_account_summary(current_prices: dict = None) -> dict:
    """Полная сводка: баланс + позиции с P&L + margin info."""
    balance_info = get_balance()
    margin_info = get_margin_level(current_prices)
    positions = get_positions()

    positions_with_pnl = []
    total_pnl = 0
    positions_value_at_current = 0

    for pos in positions:
        ticker = pos["ticker"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        side = pos["side"]
        commission = pos["commission"] or 0
        leverage = pos.get("leverage", 1.0) or 1.0
        pos_borrowed = pos.get("borrowed", 0) or 0

        current = entry
        if current_prices and ticker in current_prices:
            current = current_prices[ticker]

        if side == "LONG":
            pnl = (current - entry) * qty
            positions_value_at_current += current * qty
        else:
            pnl = (entry - current) * qty
            positions_value_at_current += current * qty

        pnl_pct = (pnl / (entry * qty) * 100) if entry * qty > 0 else 0
        total_pnl += pnl

        # Liquidation price
        liq_price = 0
        if leverage > 1 and pos_borrowed > 0:
            if side == "LONG":
                liq_price = entry * (1 - 1 / leverage)
            else:
                liq_price = entry * (1 + 1 / leverage)

        positions_with_pnl.append({
            "trade_id": pos["trade_id"],
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "entry_price": entry,
            "current_price": current,
            "stop_loss": pos["stop_loss"],
            "take_profit": pos["take_profit"],
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
            "commission": commission,
            "strategy": pos["strategy"],
            "opened_at": pos["opened_at"],
            "leverage": leverage,
            "borrowed": round(pos_borrowed, 2),
            "liquidation_price": round(liq_price, 2) if liq_price > 0 else None,
        })

    total_value = balance_info["current_balance"] + positions_value_at_current

    return {
        "initial_capital": balance_info["initial_capital"],
        "current_balance": balance_info["current_balance"],
        "borrowed": balance_info["borrowed"],
        "positions_value": round(positions_value_at_current, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "positions": positions_with_pnl,
        "positions_count": len(positions_with_pnl),
        "margin_level": margin_info["margin_level"],
        "margin_call": margin_info["margin_call"],
        "liquidation": margin_info["liquidation"],
        "leverage_used": margin_info["leverage_used"],
        "own_capital": margin_info["own_capital"],
    }


def reset_account(initial_capital: float = 100000):
    """Сбросить виртуальный счёт."""
    _ensure_columns()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM virtual_positions")
    cursor.execute(
        "UPDATE virtual_account SET initial_capital = ?, current_balance = ?, borrowed = 0, updated_at = ? WHERE id = 1",
        (initial_capital, initial_capital, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    logger.info(f"Virtual account reset: {initial_capital} RUB")


def update_stop_loss(trade_id: str, new_stop_loss: float) -> dict:
    """Обновить стоп-лосс для виртуальной позиции."""
    datetime.now(timezone.utc).isoformat()

    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM virtual_positions WHERE trade_id = ? AND status = 'open'",
        (trade_id,),
    )
    pos = cursor.fetchone()

    if not pos:
        conn.close()
        return {"status": "error", "reason": "position_not_found"}

    old_stop = pos["stop_loss"]
    cursor.execute(
        "UPDATE virtual_positions SET stop_loss = ? WHERE trade_id = ?",
        (new_stop_loss, trade_id),
    )
    conn.commit()
    conn.close()

    logger.info(f"Stop loss updated: {trade_id} | {old_stop:.2f} → {new_stop_loss:.2f}")
    return {
        "status": "updated",
        "trade_id": trade_id,
        "old_stop": old_stop,
        "new_stop": new_stop_loss,
    }
