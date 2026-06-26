"""Maximum drawdown checks and circuit breaker for portfolio protection."""

import logging

logger = logging.getLogger(__name__)

HALT_FILE = "data/.drawdown_halt"


def get_peak_equity() -> float:
    """Get historical peak equity from snapshots."""
    from tools.memory import _query
    rows = _query("SELECT MAX(total_value) as peak FROM equity_snapshots", fetch=True, one=True)
    return rows["peak"] if rows else 0.0


def check_drawdown(current_equity: float, config: dict) -> dict:
    """Check drawdown limits.

    Returns:
        {"triggered": bool, "action": "ok"|"pause"|"halt", "drawdown": float}
    """
    peak = get_peak_equity()
    if peak <= 0 or current_equity <= 0:
        return {"triggered": False, "action": "ok", "drawdown": 0.0}

    drawdown = max(0.0, (peak - current_equity) / peak * 100)
    trading_config = config.get("trading", {})
    max_daily = trading_config.get("max_daily_drawdown", 5.0)
    max_total = trading_config.get("max_total_drawdown", 15.0)

    if drawdown >= max_total:
        logger.critical(f"MAX TOTAL DRAWDOWN: {drawdown:.1f}% >= {max_total}% — halting trading")
        return {"triggered": True, "action": "halt", "drawdown": round(drawdown, 2)}

    if drawdown >= max_daily:
        logger.warning(f"DAILY DRAWDOWN: {drawdown:.1f}% >= {max_daily}% — pausing new trades")
        return {"triggered": True, "action": "pause", "drawdown": round(drawdown, 2)}

    return {"triggered": False, "action": "ok", "drawdown": round(drawdown, 2)}
