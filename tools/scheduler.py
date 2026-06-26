"""Trading Scheduler — фоновый запуск торговых циклов по расписанию."""

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TradingScheduler:
    """Циклический запуск торговых циклов в фоновом потоке."""

    def __init__(self, supervisor: Any, config: Optional[dict] = None):
        self._supervisor = supervisor
        self._config = config or {}
        self._thread = None
        self._running = False
        self._interval_minutes = self._config.get("schedule", {}).get("cycle_interval_minutes", 15)
        self._tickers = self._config.get("watchlist", ["SBER"])

        # Trading hours config
        schedule = self._config.get("schedule", {})
        self._trading_hours = schedule.get("trading_hours", "10:00-18:45")
        self._timezone = schedule.get("timezone", "Europe/Moscow")

        self._lock = threading.Lock()
        self._last_run = None
        self._next_run = None
        self._cycles_run = 0
        self._current_cycle_id = None

        # SQLite logs
        self._init_scheduler_db()

    def _init_scheduler_db(self) -> None:
        """Инициализация таблицы логов планировщика."""
        try:
            from tools.memory import get_db_path
            conn = sqlite3.connect(get_db_path())
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduler_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT,
                    timestamp TEXT,
                    tickers TEXT,
                    proposals INTEGER,
                    approved INTEGER,
                    executed INTEGER,
                    errors INTEGER,
                    error_msg TEXT,
                    capital REAL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to init scheduler DB: {e}")

    def _is_trading_hours(self) -> bool:
        """Проверяет, находятся ли текущие часы в рамках trading_hours."""
        try:
            # Парсим "10:00-18:45"
            parts = self._trading_hours.split("-")
            if len(parts) != 2:
                return True  # Если формат неверен, разрешаем торговлю

            start_h, start_m = map(int, parts[0].split(":"))
            end_h, end_m = map(int, parts[1].split(":"))

            # Используем московское время (UTC+3)
            now_utc = datetime.now(timezone.utc)
            now_msk = now_utc + timedelta(hours=3)

            current_minutes = now_msk.hour * 60 + now_msk.minute
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            return start_minutes <= current_minutes <= end_minutes
        except Exception as e:
            logger.warning(f"Failed to parse trading_hours '{self._trading_hours}': {e}")
            return True  # Fallback: разрешаем торговлю

    def _is_trading_day(self) -> bool:
        """Проверяет, является ли сегодня торговый день (пн-пт)."""
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc + timedelta(hours=3)
        # Понедельник=0, Воскресенье=6
        return now_msk.weekday() < 5

    def start(self, interval_minutes: Optional[int] = None, tickers: Optional[list] = None) -> bool:
        """Запуск фонового потока."""
        if self._running:
            logger.warning("Scheduler already running")
            return False

        if interval_minutes:
            self._interval_minutes = interval_minutes
        if tickers:
            self._tickers = tickers

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="TradingScheduler")
        self._thread.start()

        logger.info(
            f"Scheduler started: interval={self._interval_minutes}min, "
            f"tickers={self._tickers}"
        )
        return True

    def stop(self) -> bool:
        """Остановка фонового потока."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("Scheduler stopped")
        return True

    def _loop(self) -> None:
        """Основной цикл: sleep → run → log → repeat."""
        # Первый запуск сразу (если trading hours)
        self._next_run = datetime.now(timezone.utc)
        if self._is_trading_day() and self._is_trading_hours():
            self._run_cycle()
        else:
            logger.info("[Scheduler] Outside trading hours, skipping first cycle")

        while self._running:
            # Ждём до следующего запуска
            while self._running and datetime.now(timezone.utc) < self._next_run:
                time.sleep(1)

            if not self._running:
                break

            # Проверяем trading hours перед каждым циклом
            if self._is_trading_day() and self._is_trading_hours():
                self._run_cycle()
            else:
                logger.debug("[Scheduler] Outside trading hours, skipping cycle")
                # Ждём 60 секунд перед следующей проверкой
                time.sleep(60)

    def _run_cycle(self) -> None:
        """Запуск одного торгового цикла."""
        cycle_id = str(uuid.uuid4())[:8]
        self._current_cycle_id = cycle_id
        self._last_run = datetime.now(timezone.utc)
        self._next_run = self._last_run + timedelta(minutes=self._interval_minutes)

        logger.info(f"[Scheduler] Starting cycle {cycle_id}")

        try:
            report = self._supervisor.run_trading_cycle(
                tickers=list(self._tickers),
                max_iterations=1,
            )

            log_entry = {
                "time": self._last_run.isoformat(),
                "cycle_id": cycle_id,
                "tickers": report.get("tickers_analyzed", []),
                "proposals": report.get("proposals_generated", 0),
                "approved": report.get("proposals_approved", 0),
                "executed": report.get("orders_placed", 0),
                "errors": len(report.get("errors", [])),
                "capital": report.get("capital", 0),
            }

            # Store in SQLite
            try:
                from tools.memory import get_db_path
                conn = sqlite3.connect(get_db_path())
                conn.execute("""
                    INSERT INTO scheduler_logs
                    (cycle_id, timestamp, tickers, proposals, approved, executed, errors, capital)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cycle_id, self._last_run.isoformat(),
                    json.dumps(log_entry["tickers"]),
                    log_entry["proposals"], log_entry["approved"],
                    log_entry["executed"], log_entry["errors"],
                    log_entry["capital"],
                ))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to store scheduler log: {e}")

            self._cycles_run += 1

            logger.info(
                f"[Scheduler] Cycle {cycle_id} done: "
                f"proposals={log_entry['proposals']}, "
                f"approved={log_entry['approved']}, "
                f"executed={log_entry['executed']}"
            )

        except Exception as e:
            logger.error(f"[Scheduler] Cycle {cycle_id} failed: {e}")
            try:
                from tools.memory import get_db_path
                conn = sqlite3.connect(get_db_path())
                conn.execute("""
                    INSERT INTO scheduler_logs
                    (cycle_id, timestamp, tickers, proposals, approved, executed, errors, error_msg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (cycle_id, self._last_run.isoformat(), "[]", 0, 0, 0, 1, str(e)))
                conn.commit()
                conn.close()
            except Exception:
                pass

        finally:
            self._current_cycle_id = None

    def get_status(self) -> dict:
        """Получить статус планировщика для дашборда."""
        recent_logs = self.get_all_logs(10)
        return {
            "running": self._running,
            "interval_minutes": self._interval_minutes,
            "tickers": self._tickers,
            "cycles_run": self._cycles_run,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": self._next_run.isoformat() if self._next_run else None,
            "current_cycle_id": self._current_cycle_id,
            "recent_logs": recent_logs,
        }

    def get_all_logs(self, limit: int = 50) -> list[dict]:
        """Получить все логи циклов из SQLite."""
        try:
            from tools.memory import get_db_path
            conn = sqlite3.connect(get_db_path())
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM scheduler_logs ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            # Parse tickers JSON
            for row in rows:
                try:
                    row["tickers"] = json.loads(row.get("tickers", "[]"))
                except (json.JSONDecodeError, TypeError):
                    row["tickers"] = []
                # Rename for dashboard compatibility
                row["time"] = row.pop("timestamp", "")
            return rows
        except Exception as e:
            logger.error(f"Failed to get scheduler logs: {e}")
            return []

    def clear_logs(self) -> None:
        """Очистить логи."""
        try:
            from tools.memory import get_db_path
            conn = sqlite3.connect(get_db_path())
            conn.execute("DELETE FROM scheduler_logs")
            conn.commit()
            conn.close()
            self._cycles_run = 0
            logger.info("Scheduler logs cleared")
        except Exception as e:
            logger.error(f"Failed to clear scheduler logs: {e}")
