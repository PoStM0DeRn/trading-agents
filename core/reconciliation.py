"""Trade reconciliation — compares local positions with broker."""

import logging

from tools.service import send_alert

logger = logging.getLogger(__name__)


def reconcile(paper_trading: bool = True) -> dict:
    """Compare local (virtual) positions with broker positions.

    In paper_trading mode, only logs current positions without comparison.
    In live mode, compares virtual_positions with broker positions
    and sends alerts on mismatches.

    Returns:
        {"status": str, "mismatches": list, "ok": bool}
    """
    if paper_trading:
        logger.info("[PAPER] Reconciliation skipped — paper trading mode")
        return {"status": "skipped", "reason": "paper_trading", "mismatches": [], "ok": True}

    try:
        from tools.virtual_portfolio import get_positions as local_positions
        from tools.execution import get_positions as broker_positions

        local = {}
        for p in local_positions():
            ticker = p.get("ticker", "")
            local[ticker] = local.get(ticker, 0) + p.get("quantity", 0)

        broker = {}
        for p in broker_positions():
            ticker = p.get("ticker", "")
            broker[ticker] = broker.get(ticker, 0) + p.get("quantity", 0)

        all_tickers = set(list(local.keys()) + list(broker.keys()))
        mismatches = []
        for ticker in sorted(all_tickers):
            lq = local.get(ticker, 0)
            bq = broker.get(ticker, 0)
            if lq != bq:
                mismatches.append({"ticker": ticker, "local": lq, "broker": bq})
                logger.error(f"[RECONCILIATION] {ticker}: local={lq} broker={bq}")
                send_alert(
                    f"RECONCILIATION MISMATCH: {ticker}\n"
                    f"Local: {lq}, Broker: {bq}",
                    severity="critical",
                )

        if mismatches:
            logger.warning(f"[RECONCILIATION] {len(mismatches)} mismatch(es) found")
            return {"status": "mismatch", "mismatches": mismatches, "ok": False}

        logger.info("[RECONCILIATION] All positions match")
        return {"status": "ok", "mismatches": [], "ok": True}

    except Exception as e:
        logger.error(f"[RECONCILIATION] Failed: {e}")
        return {"status": "error", "error": str(e), "mismatches": [], "ok": False}
