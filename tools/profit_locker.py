"""Profit Locker — фиксация прибыли на портфельном уровне.

Когда equity портфеля достигает initial_capital × (1 + profit_target_percent / 100):
1. Закрываются ВСЕ открытые позиции
2. Прибыль фиксируется
3. Следующий цикл — пауза (новые сделки не открываются)
4. После паузы — обновление initial_capital до текущего equity, продолжение торговли
"""

import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_conn():
    from tools.memory import get_raw_conn
    return get_raw_conn(check_same_thread=False)


def check_profit_target(equity: float, initial_capital: float, target_percent: float) -> dict:
    """Проверить, достигнут ли portfolio take-profit.

    Args:
        equity: Текущий equity портфеля (own_capital)
        initial_capital: Начальный/базовый капитал
        target_percent: Целевой процент прибыли (0 = выключено)

    Returns:
        {"triggered": bool, "equity": float, "target": float, "profit_pct": float}
    """
    if target_percent <= 0:
        return {"triggered": False, "equity": equity, "target": 0, "profit_pct": 0}

    target_equity = initial_capital * (1 + target_percent / 100)
    profit_pct = ((equity - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0

    triggered = equity >= target_equity

    if triggered:
        logger.info(
            f"[ProfitLocker] TARGET HIT: equity={equity:.2f} >= target={target_equity:.2f} "
            f"(+{profit_pct:.1f}% from {initial_capital:.2f})"
        )

    return {
        "triggered": triggered,
        "equity": round(equity, 2),
        "target": round(target_equity, 2),
        "profit_pct": round(profit_pct, 2),
        "initial_capital": round(initial_capital, 2),
    }


def record_profit_lock(
    equity: float, initial_capital: float, target_percent: float,
    total_pnl: float, positions_closed: int, unlock_after_cycle: int,
):
    """Записать событие фиксации прибыли."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO profit_locks
            (locked_at, equity, initial_capital, target_percent, target_equity,
             positions_closed, total_pnl, unlock_after_cycle, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (
            now, equity, initial_capital, target_percent,
            initial_capital * (1 + target_percent / 100),
            positions_closed, total_pnl, unlock_after_cycle,
        ))
        conn.commit()
        conn.close()
        logger.info(
            f"[ProfitLocker] Recorded: equity={equity:.2f}, pnl={total_pnl:+.2f}, "
            f"positions_closed={positions_closed}, unlock_after_cycle={unlock_after_cycle}"
        )
    except Exception as e:
        logger.error(f"[ProfitLocker] Failed to record: {e}")


def should_skip_cycle(cycle_count: int) -> dict:
    """Проверить, нужно ли пропускать текущий цикл (пауза после фиксации).

    Returns:
        {"skip": bool, "reason": str, "lock_info": dict | None, "just_expired": bool}
    """
    try:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM profit_locks WHERE status = 'active' ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"skip": False, "reason": "", "lock_info": None, "just_expired": False}

        lock = dict(row)
        unlock_cycle = lock["unlock_after_cycle"]

        if cycle_count <= unlock_cycle:
            return {
                "skip": True,
                "reason": f"Profit lock active — pause until cycle {unlock_cycle + 1}",
                "lock_info": lock,
                "just_expired": False,
            }

        # Пауза закончилась — деактивировать запись
        _expire_lock(lock["id"])
        return {
            "skip": False,
            "reason": "",
            "lock_info": lock,
            "just_expired": True,
        }

    except Exception as e:
        logger.error(f"[ProfitLocker] should_skip_cycle error: {e}")
        return {"skip": False, "reason": "", "lock_info": None, "just_expired": False}


def get_lock_status() -> dict:
    """Получить текущий статус фиксации прибыли."""
    try:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM profit_locks ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"is_locked": False, "history": []}

        lock = dict(row)
        return {
            "is_locked": lock["status"] == "active",
            "last_lock": lock,
        }
    except Exception:
        return {"is_locked": False, "history": []}


def update_initial_capital(new_capital: float):
    """Обновить initial_capital в virtual_account после фиксации прибыли."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE virtual_account SET initial_capital = ?, updated_at = ? WHERE id = 1",
            (new_capital, now),
        )
        conn.commit()
        conn.close()
        logger.info(f"[ProfitLocker] initial_capital updated to {new_capital:.2f}")
    except Exception as e:
        logger.error(f"[ProfitLocker] Failed to update initial_capital: {e}")


def _expire_lock(lock_id: int):
    """Деактивировать запись о фиксации."""
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE profit_locks SET status = 'expired' WHERE id = ?", (lock_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[ProfitLocker] Failed to expire lock {lock_id}: {e}")


def get_lock_history(limit: int = 20) -> list[dict]:
    """История фиксаций прибыли."""
    try:
        conn = _get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM profit_locks ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []
