"""Margin Monitor — проверка маржинального уровня и ликвидации позиций."""

import logging

logger = logging.getLogger(__name__)


def check_margin_level(current_prices: dict = None) -> dict:
    """Проверить текущий маржинальный уровень.

    Returns:
        {
            "margin_level": float,
            "margin_call": bool,
            "liquidation": bool,
            "positions_to_liquidate": [...],
            "status": "ok" | "margin_call" | "liquidation",
        }
    """
    from tools.virtual_portfolio import get_margin_level, get_positions

    margin = get_margin_level(current_prices)

    positions_to_liquidate = []

    if margin["liquidation"]:
        logger.critical(
            f"[MarginMonitor] LIQUIDATION TRIGGERED: margin_level={margin['margin_level']:.1f}% "
            f"< 30% threshold"
        )
        # Ликвидируем ВСЕ позиции (принудительное закрытие)
        positions_to_liquidate = get_positions()
        status = "liquidation"

    elif margin["margin_call"]:
        logger.warning(
            f"[MarginMonitor] MARGIN CALL: margin_level={margin['margin_level']:.1f}% "
            f"< 50% threshold — need to reduce exposure"
        )
        # При margin call — ликвидируем самую убыточную позицию
        positions = get_positions()
        if positions:
            worst = _find_worst_position(positions, current_prices)
            if worst:
                positions_to_liquidate = [worst]
        status = "margin_call"

    else:
        status = "ok"

    return {
        "margin_level": margin["margin_level"],
        "margin_call": margin["margin_call"],
        "liquidation": margin["liquidation"],
        "leverage_used": margin["leverage_used"],
        "own_capital": margin["own_capital"],
        "borrowed": margin["borrowed"],
        "positions_to_liquidate": [
            {
                "trade_id": p["trade_id"],
                "ticker": p["ticker"],
                "side": p["side"],
                "quantity": p["quantity"],
                "entry_price": p["entry_price"],
            }
            for p in positions_to_liquidate
        ],
        "status": status,
    }


def execute_liquidation(positions_to_close: list[dict], current_prices: dict = None) -> dict:
    """Принудительно закрыть позиции при margin call / liquidation.

    positions_to_close: [{"trade_id": "...", "ticker": "...", "side": "...", "quantity": ...}]
    """
    from tools.virtual_portfolio import close_position
    from tools.market_data import get_current_quote

    results = []
    total_pnl = 0

    for pos in positions_to_close:
        trade_id = pos.get("trade_id")
        ticker = pos.get("ticker")

        # Получаем текущую цену
        price = 0
        if current_prices and ticker in current_prices:
            price = current_prices[ticker]
        else:
            try:
                q = get_current_quote(ticker)
                price = q.get("last", q.get("bid" if pos.get("side") == "LONG" else "ask", 0))
            except Exception as e:
                logger.error(f"Failed to get price for liquidation of {ticker}: {e}")
                # Используем entry_price как последний шанс
                price = pos.get("entry_price", 0)

        if price <= 0:
            logger.error(f"Cannot liquidate {ticker}: no price available")
            results.append({
                "trade_id": trade_id,
                "status": "error",
                "reason": "no_price",
            })
            continue

        result = close_position(trade_id=trade_id, close_price=price)
        pnl = result.get("pnl", 0)
        total_pnl += pnl

        logger.info(
            f"[Liquidation] Closed {ticker} ({pos.get('side')}) @ {price:.2f} | P&L={pnl:+.2f}"
        )
        results.append({
            "trade_id": trade_id,
            "ticker": ticker,
            "side": pos.get("side"),
            "quantity": pos.get("quantity"),
            "close_price": price,
            "pnl": pnl,
            "status": result.get("status", "error"),
        })

    return {
        "positions_closed": len([r for r in results if r.get("status") == "closed"]),
        "total_pnl": round(total_pnl, 2),
        "results": results,
    }


def _find_worst_position(positions: list[dict], current_prices: dict = None) -> dict | None:
    """Найти самую убыточную позицию (для частичной ликвидации при margin call)."""
    from tools.market_data import get_current_quote

    worst = None
    worst_pnl = 0

    for pos in positions:
        ticker = pos["ticker"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        side = pos["side"]

        price = entry
        if current_prices and ticker in current_prices:
            price = current_prices[ticker]
        else:
            try:
                q = get_current_quote(ticker)
                price = q.get("last", entry)
            except Exception:
                pass

        if side == "LONG":
            pnl = (price - entry) * qty
        else:
            pnl = (entry - price) * qty

        if pnl < worst_pnl:
            worst_pnl = pnl
            worst = pos

    return worst
