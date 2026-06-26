"""Инструменты памяти и аналитики."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from contextlib import contextmanager

logger = logging.getLogger(__name__)

_db_path = "data/trading_memory.db"


def get_db_path() -> str:
    """Получить текущий путь к БД."""
    return _db_path


@contextmanager
def _get_conn():
    """Context manager for safe DB connections (auto-close on error)."""
    conn = sqlite3.connect(_db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def get_raw_conn(check_same_thread: bool = True):
    """Get a raw DB connection (caller must close it)."""
    conn = sqlite3.connect(_db_path, check_same_thread=check_same_thread, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Public alias for context manager use by other modules
get_conn = _get_conn


def _query(query: str, params: tuple = (), *, fetch: bool = False, one: bool = False):
    """Execute a query safely. If fetch=True, returns rows as dicts."""
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch:
            rows = cursor.fetchall()
            return [dict(r) for r in rows] if not one else (dict(rows[0]) if rows else None)
        conn.commit()
        return None


def init_db(db_path: str = None):
    """Инициализация базы данных."""
    global _db_path
    if db_path:
        _db_path = db_path

    with _get_conn() as conn:
        cursor = conn.cursor()

        for ddl in [
            """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT UNIQUE, ticker TEXT,
                action TEXT, quantity INTEGER, entry_price REAL, exit_price REAL,
                stop_loss REAL, take_profit REAL, pnl REAL, commission REAL,
                strategy TEXT, signal_context TEXT, rationale TEXT,
                opened_at TEXT, closed_at TEXT, status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, ticker TEXT,
                description TEXT, impact_score REAL, sentiment TEXT, source TEXT,
                timestamp TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name TEXT, action TEXT,
                input_data TEXT, output_data TEXT, tool_calls TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS trade_context (
                trade_id TEXT PRIMARY KEY, ticker TEXT, rsi REAL, macd_signal TEXT,
                bb_position TEXT, atr REAL, volatility_regime TEXT, trend TEXT,
                volume_vs_avg REAL, sentiment_score REAL, sentiment_label TEXT,
                support REAL, resistance REAL, price_at_entry REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS trade_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT,
                ticker TEXT, strategy TEXT, lesson_type TEXT,
                pattern_description TEXT, conditions TEXT, confidence REAL,
                times_observed INTEGER, times_lost INTEGER, win_rate REAL,
                severity TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS virtual_account (
                id INTEGER PRIMARY KEY AUTOINCREMENT, initial_capital REAL DEFAULT 100000,
                current_balance REAL DEFAULT 100000, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS virtual_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id TEXT UNIQUE,
                ticker TEXT, side TEXT, quantity INTEGER, entry_price REAL,
                stop_loss REAL, take_profit REAL, status TEXT DEFAULT 'open',
                opened_at TEXT DEFAULT CURRENT_TIMESTAMP, closed_at TEXT,
                close_price REAL, pnl REAL DEFAULT 0, commission REAL DEFAULT 0,
                strategy TEXT, rationale TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                total_value REAL, balance REAL, positions_value REAL, pnl REAL,
                borrowed REAL, margin_level REAL, positions_count INTEGER, cycle_id TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS config_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                section TEXT, param TEXT, old_value TEXT, new_value TEXT,
                source TEXT DEFAULT 'dashboard'
            )""",
            """CREATE TABLE IF NOT EXISTS profit_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, locked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                equity REAL, initial_capital REAL, target_percent REAL, target_equity REAL,
                positions_closed INTEGER DEFAULT 0, total_pnl REAL DEFAULT 0,
                unlock_after_cycle INTEGER DEFAULT 0, status TEXT DEFAULT 'active'
            )""",
            """CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, scan_time TEXT DEFAULT CURRENT_TIMESTAMP,
                method TEXT DEFAULT 'filter', total_scanned INTEGER DEFAULT 0,
                filtered_count INTEGER DEFAULT 0, selected_count INTEGER DEFAULT 0,
                market_outlook TEXT DEFAULT 'neutral', selected_tickers TEXT DEFAULT '[]',
                all_candidates TEXT DEFAULT '[]'
            )""",
        ]:
            cursor.execute(ddl)

        # Schema migrations
        for col in [
            ("idempotency_key", "TEXT UNIQUE"),
            ("broker_order_id", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError:
                pass

        cursor.execute("SELECT COUNT(*) FROM virtual_account")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO virtual_account (initial_capital, current_balance) VALUES (100000, 100000)")

        conn.commit()


def store_equity_snapshot(total_value: float, balance: float, positions_value: float,
                          pnl: float, borrowed: float = 0, margin_level: float = 0,
                          positions_count: int = 0, cycle_id: str = None) -> bool:
    """Сохранить снимок equity для построения кривой капитала."""
    try:
        _query(
            "INSERT INTO equity_snapshots (total_value, balance, positions_value, pnl, borrowed, margin_level, positions_count, cycle_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (total_value, balance, positions_value, pnl, borrowed, margin_level, positions_count, cycle_id),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store equity snapshot: {e}")
        return False


def get_equity_history(limit: int = 500) -> list[dict]:
    """Получить историю equity curve."""
    try:
        return _query("SELECT * FROM equity_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,), fetch=True)
    except Exception as e:
        logger.error(f"Failed to get equity history: {e}")
        return []


def store_trade(trade_record: dict) -> bool:
    """Сохранить запись о сделке."""
    try:
        _query(
            "INSERT OR REPLACE INTO trades (trade_id, ticker, action, quantity, entry_price, exit_price, stop_loss, take_profit, pnl, commission, strategy, signal_context, rationale, opened_at, closed_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trade_record.get("trade_id"), trade_record.get("ticker"), trade_record.get("action"),
                trade_record.get("quantity"), trade_record.get("entry_price"), trade_record.get("exit_price"),
                trade_record.get("stop_loss"), trade_record.get("take_profit"), trade_record.get("pnl"),
                trade_record.get("commission"), trade_record.get("strategy"),
                json.dumps(trade_record.get("signal_context", {})), trade_record.get("rationale"),
                trade_record.get("opened_at"), trade_record.get("closed_at"), trade_record.get("status", "open"),
            ),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store trade: {e}")
        return False


def get_trade_by_idempotency_key(key: str) -> Optional[dict]:
    """Find trade by idempotency key. Returns None if not found."""
    if not key:
        return None
    try:
        return _query("SELECT * FROM trades WHERE idempotency_key = ?", (key,), fetch=True, one=True)
    except Exception as e:
        logger.error(f"Failed to lookup idempotency key: {e}")
        return None


def find_similar_trades(
    limit: int = 5,
    ticker: Optional[str] = None,
    action: Optional[str] = None,
    strategy: Optional[str] = None,
    query_embedding: list = None,
) -> list[dict]:
    """Поиск исторических сделок по критериям."""
    try:
        q = "SELECT * FROM trades WHERE status = 'closed'"
        params = []
        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)
        if action:
            q += " AND action = ?"
            params.append(action)
        if strategy:
            q += " AND strategy = ?"
            params.append(strategy)
        q += " ORDER BY closed_at DESC LIMIT ?"
        params.append(limit)
        return _query(q, tuple(params), fetch=True)
    except Exception as e:
        logger.error(f"Failed to find similar trades: {e}")
        return []


def get_trade_statistics(
    strategy_name: Optional[str] = None, period: Optional[str] = None
) -> dict:
    """Статистика сделок: win rate, profit factor, средний R/R, Sharpe, Sortino, Max DD."""
    try:
        q = "SELECT * FROM trades WHERE status = 'closed'"
        params = []
        if strategy_name:
            q += " AND strategy = ?"
            params.append(strategy_name)
        if period:
            period_map = {"day": "-1 day", "week": "-7 days", "month": "-1 month", "year": "-1 year"}
            if period in period_map:
                q += f" AND closed_at >= datetime('now', '{period_map[period]}')"
        trades = _query(q, tuple(params), fetch=True)

        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "avg_rr_ratio": 0,
                "total_pnl": 0,
                "sharpe_ratio": 0,
                "sortino_ratio": 0,
                "max_drawdown": 0,
            }

        wins = [t for t in trades if (t.get("pnl") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl") or 0) <= 0]

        total_profit = sum(t.get("pnl", 0) for t in wins)
        total_loss = abs(sum(t.get("pnl", 0) for t in losses))

        # Calculate Sharpe, Sortino, Max DD from equity snapshots
        pnls = [t.get("pnl", 0) for t in trades]
        sharpe_ratio = 0
        sortino_ratio = 0
        max_drawdown = 0

        if pnls:
            import numpy as np
            avg_return = np.mean(pnls)
            std_return = np.std(pnls) if len(pnls) > 1 else 0
            downside_std = np.std([p for p in pnls if p < 0]) if any(p < 0 for p in pnls) else 0

            if std_return > 0:
                sharpe_ratio = avg_return / std_return
            if downside_std > 0:
                sortino_ratio = avg_return / downside_std

            # Max drawdown from equity snapshots
            equity_history = get_equity_history()
            if equity_history:
                values = [e.get("total_value", 0) for e in equity_history]
                peak = values[0] if values else 0
                max_dd = 0
                for val in values:
                    if val > peak:
                        peak = val
                    dd = (peak - val) / peak * 100 if peak > 0 else 0
                    if dd > max_dd:
                        max_dd = dd
                max_drawdown = max_dd

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 2),
            "profit_factor": round(total_profit / total_loss, 2) if total_loss > 0 else float("inf"),
            "avg_pnl": round(sum(t.get("pnl", 0) for t in trades) / len(trades), 2),
            "total_pnl": round(sum(t.get("pnl", 0) for t in trades), 2),
            "total_commission": round(sum(t.get("commission", 0) for t in trades), 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
        }
    except Exception as e:
        logger.error(f"Failed to get trade statistics: {e}")
        return {"error": str(e)}


def store_event(event_record: dict) -> bool:
    """Сохранить важное рыночное событие."""
    try:
        _query(
            "INSERT INTO events (event_type, ticker, description, impact_score, sentiment, source, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_record.get("event_type"), event_record.get("ticker"),
                event_record.get("description"), event_record.get("impact_score"),
                event_record.get("sentiment"), event_record.get("source"),
                event_record.get("timestamp", datetime.now(timezone.utc).isoformat()),
            ),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store event: {e}")
        return False


def log_agent_action(agent_name: str, action: str, input_data: dict, output_data: dict, tool_calls: list = None):
    """Логирование действий агента."""
    try:
        _query(
            "INSERT INTO agent_logs (agent_name, action, input_data, output_data, tool_calls) VALUES (?, ?, ?, ?, ?)",
            (agent_name, action, json.dumps(input_data), json.dumps(output_data), json.dumps(tool_calls or [])),
        )
    except Exception as e:
        logger.error(f"Failed to log agent action: {e}")


def get_all_trades(status: str = None, limit: int = 100) -> list[dict]:
    """Получить все сделки для дашборда."""
    try:
        if status:
            return _query("SELECT * FROM trades WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit), fetch=True)
        return _query("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,), fetch=True)
    except Exception as e:
        logger.error(f"Failed to get trades: {e}")
        return []


def get_agent_logs(limit: int = 100, agent_name: str = None) -> list[dict]:
    """Получить логи агентов для дашборда."""
    try:
        if agent_name:
            return _query("SELECT * FROM agent_logs WHERE agent_name = ? ORDER BY timestamp DESC LIMIT ?", (agent_name, limit), fetch=True)
        return _query("SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT ?", (limit,), fetch=True)
    except Exception as e:
        logger.error(f"Failed to get agent logs: {e}")
        return []


# ──────────────────────────────────────────────────────────────────
# LEARNING FROM LOSSES — контекст, анализ, уроки
# ──────────────────────────────────────────────────────────────────


def _extract_rsi_bucket(rsi):
    if rsi is None:
        return None
    if rsi < 30:
        return "oversold"
    if rsi < 45:
        return "low"
    if rsi < 55:
        return "neutral"
    if rsi < 70:
        return "high"
    return "overbought"


def store_trade_context(
    trade_id: str,
    ticker: str,
    market_snapshot: dict = None,
    news_briefing: dict = None,
) -> bool:
    """Сохранить рыночный контекст при открытии сделки."""
    ms = market_snapshot or {}
    nb = news_briefing or {}

    indicators = ms.get("indicators", {})
    quote = ms.get("quote", {})
    news = nb.get("overall_sentiment", nb.get("sentiment", {}))

    if isinstance(news, str):
        sentiment_score = 0.0
        sentiment_label = news
    elif isinstance(news, dict):
        sentiment_score = float(news.get("score", news.get("compound", 0)))
        sentiment_label = news.get("label", news.get("sentiment", "neutral"))
    else:
        sentiment_score = 0.0
        sentiment_label = "neutral"

    rsi = indicators.get("rsi")
    macd_data = indicators.get("macd", {})
    if isinstance(macd_data, dict):
        macd_signal = macd_data.get("signal", "neutral")
    else:
        macd_signal = "neutral"

    bb = indicators.get("bollinger", {})
    if isinstance(bb, dict):
        bb_position = bb.get("position", "near_middle")
    else:
        bb_position = "near_middle"

    atr = indicators.get("atr", indicators.get("ATR", 0))
    if isinstance(atr, dict):
        atr = atr.get("value", 0)

    vol = quote.get("volume", 0)
    avg_vol = indicators.get("avg_volume", indicators.get("average_volume", vol))
    volume_vs_avg = vol / avg_vol if avg_vol and avg_vol > 0 else 1.0

    trend = indicators.get("trend", "sideways")
    if isinstance(trend, dict):
        trend = trend.get("direction", "sideways")

    volatility = indicators.get("volatility_regime", indicators.get("volatility", "medium"))
    if isinstance(volatility, dict):
        volatility = volatility.get("regime", "medium")

    support = indicators.get("support", quote.get("low", 0))
    resistance = indicators.get("resistance", quote.get("high", 0))
    price = quote.get("price", quote.get("close", 0))

    try:
        _query(
            "INSERT OR REPLACE INTO trade_context (trade_id, ticker, rsi, macd_signal, bb_position, atr, volatility_regime, trend, volume_vs_avg, sentiment_score, sentiment_label, support, resistance, price_at_entry) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_id, ticker, rsi, macd_signal, bb_position, atr, volatility, trend, volume_vs_avg, sentiment_score, sentiment_label, support, resistance, price),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store trade context: {e}")
        return False


def get_trade_context(trade_id: str) -> dict:
    """Получить контекст сделки."""
    try:
        return _query("SELECT * FROM trade_context WHERE trade_id = ?", (trade_id,), fetch=True, one=True) or {}
    except Exception as e:
        logger.error(f"Failed to get trade context: {e}")
        return {}


def _extract_conditions(context: dict) -> dict:
    """Извлечь условия из trade_context для сравнения паттернов."""
    if not context:
        return {}
    return {
        "rsi_bucket": _extract_rsi_bucket(context.get("rsi")),
        "macd_signal": context.get("macd_signal"),
        "bb_position": context.get("bb_position"),
        "volatility_regime": context.get("volatility_regime"),
        "trend": context.get("trend"),
        "sentiment_label": context.get("sentiment_label"),
    }


def analyze_loss_pattern(ticker: str, strategy: str = None, min_trades: int = 3) -> list[dict]:
    """SQL-анализ: найти паттерны с низким win_rate."""
    try:
        q = """
            SELECT t.ticker, t.strategy, tc.volatility_regime, tc.sentiment_label,
                CASE WHEN tc.rsi < 30 THEN 'oversold' WHEN tc.rsi < 45 THEN 'low'
                     WHEN tc.rsi < 55 THEN 'neutral' WHEN tc.rsi < 70 THEN 'high' ELSE 'overbought' END as rsi_bucket,
                COUNT(*) as times_observed,
                SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) as times_lost,
                ROUND(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate,
                ROUND(AVG(t.pnl), 2) as avg_pnl, ROUND(SUM(t.pnl), 2) as total_pnl
            FROM trades t JOIN trade_context tc ON t.trade_id = tc.trade_id
            WHERE t.status = 'closed' AND t.ticker = ? AND t.pnl < 0
        """
        params = [ticker]
        if strategy:
            q += " AND t.strategy = ?"
            params.append(strategy)
        q += " GROUP BY t.ticker, t.strategy, tc.volatility_regime, tc.sentiment_label, rsi_bucket HAVING times_observed >= ? AND win_rate < 50 ORDER BY win_rate ASC, times_observed DESC"
        params.append(min_trades)
        return _query(q, tuple(params), fetch=True)
    except Exception as e:
        logger.error(f"Failed to analyze loss patterns: {e}")
        return []


def get_strategy_performance(ticker: str, strategy: str) -> dict:
    """Статистика конкретной стратегии на конкретном тикере."""
    try:
        row = _query(
            "SELECT COUNT(*) as total_trades, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses, ROUND(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate, ROUND(AVG(pnl), 2) as avg_pnl, ROUND(SUM(pnl), 2) as total_pnl, ROUND(SUM(commission), 2) as total_commission FROM trades WHERE status = 'closed' AND ticker = ? AND strategy = ?",
            (ticker, strategy), fetch=True, one=True,
        )
        return row or {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0, "total_commission": 0}
    except Exception as e:
        logger.error(f"Failed to get strategy performance: {e}")
        return {"error": str(e)}


def store_lesson(lesson: dict) -> bool:
    """Сохранить урок (anti-pattern)."""
    try:
        _query(
            "INSERT INTO trade_lessons (trade_id, ticker, strategy, lesson_type, pattern_description, conditions, confidence, times_observed, times_lost, win_rate, severity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lesson.get("trade_id"), lesson.get("ticker"), lesson.get("strategy"),
                lesson.get("lesson_type", "pattern"), lesson.get("pattern_description"),
                json.dumps(lesson.get("conditions", {})), lesson.get("confidence", 0.5),
                lesson.get("times_observed", 0), lesson.get("times_lost", 0),
                lesson.get("win_rate", 0), lesson.get("severity", "warning"),
            ),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store lesson: {e}")
        return False


def get_relevant_warnings(ticker: str, strategy: str = None, current_conditions: dict = None, limit: int = 10) -> list[dict]:
    """Найти релевантные предупреждения для текущих условий."""
    try:
        q = "SELECT * FROM trade_lessons WHERE ticker = ?"
        params = [ticker]
        if strategy:
            q += " AND (strategy = ? OR strategy IS NULL)"
            params.append(strategy)
        q += " ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, confidence DESC, times_lost DESC LIMIT ?"
        params.append(limit)
        lessons = _query(q, tuple(params), fetch=True)

        if current_conditions and lessons:
            def _match_score(lesson):
                try:
                    conds = json.loads(lesson.get("conditions", "{}"))
                except (json.JSONDecodeError, TypeError):
                    conds = {}
                return sum(1 for k, v in current_conditions.items() if k in conds and conds[k] == v)
            lessons.sort(key=_match_score, reverse=True)

        return lessons
    except Exception as e:
        logger.error(f"Failed to get relevant warnings: {e}")
        return []


def get_critical_blocks(ticker: str, strategy: str = None) -> list[dict]:
    """Получить критические блокировки (severity=critical)."""
    try:
        q = "SELECT * FROM trade_lessons WHERE ticker = ? AND severity = 'critical'"
        params = [ticker]
        if strategy:
            q += " AND (strategy = ? OR strategy IS NULL)"
            params.append(strategy)
        return _query(q, tuple(params), fetch=True)
    except Exception as e:
        logger.error(f"Failed to get critical blocks: {e}")
        return []


def cleanup_old_data(retention_days: int = 90) -> dict[str, int]:
    """Delete records older than retention_days.

    Returns {table: deleted_count}.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    results = {}
    deletions = {
        "agent_logs": "DELETE FROM agent_logs WHERE timestamp < ?",
        "events": "DELETE FROM events WHERE created_at < ?",
        "equity_snapshots": "DELETE FROM equity_snapshots WHERE timestamp < ?",
        "trade_lessons": "DELETE FROM trade_lessons WHERE created_at < ?",
        "config_audit": "DELETE FROM config_audit WHERE timestamp < ?",
    }
    for table, sql in deletions.items():
        try:
            _query(sql, (cutoff,))
            results[table] = "cleaned"
            logger.info(f"Cleanup: {table} older than {retention_days}d")
        except Exception as e:
            logger.warning(f"Cleanup failed for {table}: {e}")
            results[table] = f"error: {e}"

    old_trades_cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days * 2)).isoformat()
    try:
        _query("DELETE FROM trades WHERE status IN ('filled', 'closed') AND closed_at < ?", (old_trades_cutoff,))
        results["trades"] = "cleaned"
    except Exception as e:
        logger.warning(f"Cleanup failed for trades: {e}")
        results["trades"] = f"error: {e}"

    try:
        row = _query("SELECT COUNT(*) as cnt FROM config_audit", fetch=True, one=True)
        if row and row.get("cnt", 0) == 0:
            _query("VACUUM")
            logger.info("Cleanup: VACUUM completed")
    except Exception as e:
        logger.warning(f"Cleanup VACUUM failed: {e}")

    return results


def get_all_lessons(ticker: str = None, strategy: str = None, limit: int = 100) -> list[dict]:
    """Получить все уроки (для дашборда)."""
    try:
        q = "SELECT * FROM trade_lessons WHERE 1=1"
        params = []
        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)
        if strategy:
            q += " AND strategy = ?"
            params.append(strategy)
        q += f" ORDER BY created_at DESC LIMIT {int(limit)}"
        return _query(q, tuple(params), fetch=True)
    except Exception as e:
        logger.error(f"Failed to get lessons: {e}")
        return []
