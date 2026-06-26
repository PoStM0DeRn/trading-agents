"""Position Monitor — автоматическая проверка SL/TP для открытых позиций."""

import logging

logger = logging.getLogger(__name__)


def check_positions_for_close(current_prices: dict) -> list[dict]:
    """Проверить все открытые позиции на срабатывание stop-loss / take-profit.

    Args:
        current_prices: {ticker: price} — текущие рыночные цены.

    Returns:
        Список позиций, которые нужно закрыть.
    """
    from tools.virtual_portfolio import get_positions

    positions = get_positions()
    closes = []

    for pos in positions:
        ticker = pos["ticker"]
        if ticker not in current_prices:
            continue

        price = current_prices[ticker]
        side = pos["side"]
        sl = pos.get("stop_loss") or 0
        tp = pos.get("take_profit") or 0
        entry = pos["entry_price"]

        reason = None

        # Stop-loss
        if side == "LONG" and sl > 0 and price <= sl:
            reason = "stop_loss"
        elif side == "SHORT" and sl > 0 and price >= sl:
            reason = "stop_loss"

        # Take-profit
        if not reason and side == "LONG" and tp > 0 and price >= tp:
            reason = "take_profit"
        elif not reason and side == "SHORT" and tp > 0 and price <= tp:
            reason = "take_profit"

        if reason:
            pnl_raw = (price - entry) * pos["quantity"] if side == "LONG" else (entry - price) * pos["quantity"]
            logger.info(
                f"[Monitor] {reason.upper()} triggered for {side} {pos['quantity']} {ticker}: "
                f"entry={entry:.2f}, current={price:.2f}, SL={sl:.2f}, TP={tp:.2f}, "
                f"pnl={pnl_raw:+.2f}"
            )
            closes.append({
                "trade_id": pos["trade_id"],
                "ticker": ticker,
                "side": side,
                "quantity": pos["quantity"],
                "entry_price": entry,
                "close_price": price,
                "reason": reason,
                "stop_loss": sl,
                "take_profit": tp,
                "strategy": pos.get("strategy", ""),
                "pnl_raw": round(pnl_raw, 2),
            })

    return closes


def execute_closes(closes: list[dict]) -> list[dict]:
    """Выполнить закрытие позиций, сработавших по SL/TP.

    Returns:
        Список результатов закрытия.
    """
    from tools.virtual_portfolio import close_position

    results = []

    for c in closes:
        trade_id = c["trade_id"]
        close_price = c["close_price"]
        reason = c["reason"]

        result = close_position(trade_id, close_price)

        if result.get("status") == "closed":
            pnl = result.get("pnl", 0)
            logger.info(
                f"[Monitor] Closed {c['side']} {c['quantity']} {c['ticker']} "
                f"@ {close_price:.2f} | reason={reason} | P&L={pnl:+.2f}"
            )
        else:
            logger.warning(f"[Monitor] Failed to close {trade_id}: {result}")

        results.append({**c, **result})

    return results


def get_positions_with_pnl(current_prices: dict = None) -> list[dict]:
    """Получить все открытые позиции с текущим P&L.

    Args:
        current_prices: {ticker: price}. Если не переданы, используется entry_price.
    """
    from tools.virtual_portfolio import get_positions

    positions = get_positions()
    result = []

    for pos in positions:
        ticker = pos["ticker"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        side = pos["side"]

        current = entry
        if current_prices and ticker in current_prices:
            current = current_prices[ticker]

        if side == "LONG":
            pnl = (current - entry) * qty
        else:
            pnl = (entry - current) * qty

        sl = pos.get("stop_loss") or 0
        tp = pos.get("take_profit") or 0

        # Расстояние до SL/TP в процентах
        sl_distance_pct = 0
        tp_distance_pct = 0
        if side == "LONG":
            if sl > 0:
                sl_distance_pct = (current - sl) / current * 100
            if tp > 0:
                tp_distance_pct = (tp - current) / current * 100
        else:
            if sl > 0:
                sl_distance_pct = (sl - current) / current * 100
            if tp > 0:
                tp_distance_pct = (current - tp) / current * 100

        result.append({
            "trade_id": pos["trade_id"],
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "entry_price": entry,
            "current_price": current,
            "stop_loss": sl,
            "take_profit": tp,
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl / (entry * qty) * 100, 2) if entry * qty > 0 else 0,
            "sl_distance_pct": round(sl_distance_pct, 2),
            "tp_distance_pct": round(tp_distance_pct, 2),
            "strategy": pos.get("strategy", ""),
            "opened_at": pos.get("opened_at", ""),
        })

    return result
