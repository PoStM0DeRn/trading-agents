"""Agent activity monitor — отслеживание состояния агентов."""

import time
import sqlite3
import logging

logger = logging.getLogger(__name__)

# Порог для определения "активного" агента (секунд)
ACTIVE_THRESHOLD = 10

# Порядок агентов в пайплайне
AGENT_PIPELINE = [
    "NewsIntelligence",
    "MarketData",
    "Strategy_trend",
    "Strategy_contrarian",
    "Strategy_bearish",
    "Critic",
    "RiskManager",
    "PortfolioManager",
    "Execution",
    "Memory",
]


class AgentMonitor:
    """Мониторинг активности агентов через SQLite."""

    def __init__(self, db_path: str = "data/trading_memory.db"):
        self.db_path = db_path

    def get_agent_states(self) -> dict:
        """Получить состояние всех агентов."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            states = {}
            now = time.time()

            for agent_name in AGENT_PIPELINE:
                cursor.execute(
                    """
                    SELECT agent_name, action, output_data, timestamp
                    FROM agent_logs
                    WHERE agent_name LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (f"%{agent_name}%",),
                )
                row = cursor.fetchone()

                if row:
                    # Парсим timestamp
                    try:
                        ts_str = row["timestamp"]
                        # SQLite timestamp format: YYYY-MM-DD HH:MM:SS
                        from datetime import datetime
                        ts = datetime.fromisoformat(ts_str).timestamp()
                        age = now - ts
                    except (ValueError, TypeError):
                        age = 999

                    is_active = age < ACTIVE_THRESHOLD
                    action = row["action"] or ""

                    # Определяем краткое описание
                    if is_active:
                        if "llm" in action.lower() or "generate" in action.lower():
                            detail = "thinking..."
                        elif "fetch" in action.lower() or "news" in action.lower():
                            detail = "fetching data"
                        elif "calculate" in action.lower() or "risk" in action.lower():
                            detail = "calculating"
                        elif "execute" in action.lower() or "order" in action.lower():
                            detail = "executing"
                        else:
                            detail = action[:20] if action else "active"
                    else:
                        detail = "idle"

                    states[agent_name] = {
                        "status": "active" if is_active else "idle",
                        "last_action": action,
                        "detail": detail,
                        "age_seconds": round(age, 1),
                        "timestamp": row["timestamp"],
                    }
                else:
                    states[agent_name] = {
                        "status": "idle",
                        "last_action": None,
                        "detail": "no history",
                        "age_seconds": None,
                        "timestamp": None,
                    }

            conn.close()
            return states

        except Exception as e:
            logger.error(f"Failed to get agent states: {e}")
            return {name: {"status": "idle", "last_action": None, "detail": "error"}
                    for name in AGENT_PIPELINE}

    def get_pipeline_progress(self) -> dict:
        """Определить текущий шаг пайплайна."""
        states = self.get_agent_states()

        current_step = None
        for name in AGENT_PIPELINE:
            state = states.get(name, {})
            if state.get("status") == "active":
                current_step = name

        # Определяем процент завершения
        if current_step and current_step in AGENT_PIPELINE:
            idx = AGENT_PIPELINE.index(current_step)
            progress = round((idx + 1) / len(AGENT_PIPELINE) * 100)
        elif current_step is None:
            # Все idle — пайплайн завершён или не запущен
            progress = 0
        else:
            progress = 0

        return {
            "current_step": current_step,
            "progress": progress,
            "agents": states,
        }

    def get_recent_logs(self, limit: int = 20) -> list[dict]:
        """Получить последние логи агентов."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT agent_name, action, input_data, output_data, timestamp
                FROM agent_logs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            logs = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return logs

        except Exception as e:
            logger.error(f"Failed to get agent logs: {e}")
            return []
