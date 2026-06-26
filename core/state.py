"""Глобальное состояние системы."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_state_file = "data/system_state.json"


class SystemState:
    """Управление состоянием торговой системы."""

    def __init__(self):
        self._state: dict = {
            "initialized": False,
            "paper_trading": True,
            "cycle_count": 0,
            "last_cycle_at": None,
            "total_pnl": 0,
            "open_positions": [],
            "pending_orders": [],
            "errors": [],
            "config": {},
        }
        self._load()

    def _load(self):
        """Загрузка состояния из файла."""
        try:
            if Path(_state_file).exists():
                with open(_state_file, "r", encoding="utf-8") as f:
                    self._state.update(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")

    def _save(self):
        """Сохранение состояния в файл."""
        try:
            Path(_state_file).parent.mkdir(parents=True, exist_ok=True)
            with open(_state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение состояния."""
        return self._state.get(key, default)

    def set(self, key: str, value: Any):
        """Установить значение состояния."""
        self._state[key] = value
        self._save()

    def increment_cycle(self):
        """Увеличить счётчик циклов."""
        self._state["cycle_count"] = self._state.get("cycle_count", 0) + 1
        self._state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def add_position(self, position: dict):
        """Добавить позицию."""
        positions = self._state.get("open_positions", [])
        positions.append(position)
        self._state["open_positions"] = positions
        self._save()

    def remove_position(self, ticker: str):
        """Удалить позицию по тикеру."""
        positions = self._state.get("open_positions", [])
        self._state["open_positions"] = [p for p in positions if p.get("ticker") != ticker]
        self._save()

    def add_error(self, error: str):
        """Добавить ошибку."""
        errors = self._state.get("errors", [])
        errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
        })
        # Ограничиваем историю ошибок
        self._state["errors"] = errors[-100:]
        self._save()

    def reset(self):
        """Сброс состояния."""
        self._state = {
            "initialized": False,
            "paper_trading": True,
            "cycle_count": 0,
            "last_cycle_at": None,
            "total_pnl": 0,
            "open_positions": [],
            "pending_orders": [],
            "errors": [],
            "config": {},
        }
        self._save()
