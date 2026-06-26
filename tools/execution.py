"""Инструменты исполнения ордеров."""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


def _check_client():
    if _client is None:
        raise RuntimeError("T-Invest client not initialized. Call set_client() first.")
    try:
        _client.ensure_connected()
    except Exception as e:
        logger.error(f"T-Invest client unavailable: {e}")
        raise RuntimeError(f"T-Invest client not available: {e}")


def _idempotency_key(ticker: str, quantity: int, side: str, price_limit: Optional[float] = None) -> str:
    """Generate idempotency key for an order."""
    raw = f"{ticker}_{side}_{quantity}_{price_limit or 'MARKET'}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def place_order(
    ticker: str,
    quantity: int,
    order_type: str = "limit",
    side: str = "BUY",
    price_limit: Optional[float] = None,
    paper_trading: bool = True,
) -> dict:
    """Разместить ордер через брокерский API."""
    _check_client()
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    if order_type == "limit" and price_limit is None:
        raise ValueError("Price limit required for limit orders")
    if side not in ("BUY", "SELL"):
        raise ValueError("Side must be BUY or SELL")

    # Idempotency check
    id_key = _idempotency_key(ticker, quantity, side, price_limit)
    from tools.memory import get_trade_by_idempotency_key
    existing = get_trade_by_idempotency_key(id_key)
    if existing:
        logger.info(f"Duplicate order detected (idempotency_key={id_key[:8]}...): {side} {quantity} {ticker}")
        return {"status": "already_placed", "order_id": existing.get("broker_order_id", "unknown")}

    # Paper trading guard
    if paper_trading:
        paper_id = f"paper_{uuid.uuid4().hex[:12]}"
        logger.info(f"[PAPER] Would place order: {side} {quantity} {ticker} @ {price_limit or 'MARKET'} -> {paper_id}")
        return {"status": "paper", "order_id": paper_id}

    result = _client.place_order(
        ticker=ticker, quantity=quantity, side=side,
        order_type=order_type, price_limit=price_limit,
    )
    logger.info(f"[LIVE] Order placed: {side} {quantity} {ticker} @ {price_limit or 'MARKET'} -> {result['order_id']}")

    # Store idempotency key
    try:
        from tools.memory import store_trade
        store_trade({
            "trade_id": result.get("order_id", ""),
            "ticker": ticker,
            "action": side,
            "quantity": quantity,
            "entry_price": price_limit or 0,
            "status": "submitted",
            "broker_order_id": result.get("order_id", ""),
        })
    except Exception as e:
        logger.warning(f"Failed to store idempotency record: {e}")

    return result


def cancel_order(order_id: str) -> bool:
    """Отменить ордер."""
    _check_client()
    success = _client.cancel_order(order_id)
    if success:
        logger.info(f"Order {order_id} cancelled")
    else:
        logger.warning(f"Failed to cancel order {order_id}")
    return success


def get_order_status(order_id: str) -> dict:
    """Проверить статус ордера."""
    _check_client()
    return _client.get_order_status(order_id)


def get_positions() -> list[dict]:
    """Список текущих открытых позиций с деталями."""
    _check_client()
    return _client.get_positions()


def get_account_balance() -> dict:
    """Баланс и доступные средства."""
    _check_client()
    return _client.get_account_balance()
