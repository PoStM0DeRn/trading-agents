"""Конечный автомат для управления торговым циклом."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class CycleState(Enum):
    """Состояния торгового цикла."""
    IDLE = "idle"
    COLLECTING_DATA = "collecting_data"
    GENERATING_PROPOSALS = "generating_proposals"
    CRITIQUING = "critiquing"
    CALCULATING_RISK = "calculating_risk"
    CHECKING_PORTFOLIO = "checking_portfolio"
    EXECUTING = "executing"
    STORING_MEMORY = "storing_memory"
    COMPLETE = "complete"
    ERROR = "error"


class TradingCycleFSM:
    """Конечный автомат торгового цикла."""

    # Допустимые переходы
    TRANSITIONS = {
        CycleState.IDLE: [CycleState.COLLECTING_DATA],
        CycleState.COLLECTING_DATA: [CycleState.GENERATING_PROPOSALS, CycleState.ERROR],
        CycleState.GENERATING_PROPOSALS: [CycleState.CRITIQUING, CycleState.ERROR],
        CycleState.CRITIQUING: [CycleState.CALCULATING_RISK, CycleState.COMPLETE],
        CycleState.CALCULATING_RISK: [CycleState.CHECKING_PORTFOLIO, CycleState.COMPLETE],
        CycleState.CHECKING_PORTFOLIO: [CycleState.EXECUTING, CycleState.COMPLETE],
        CycleState.EXECUTING: [CycleState.STORING_MEMORY, CycleState.COMPLETE],
        CycleState.STORING_MEMORY: [CycleState.COMPLETE],
        CycleState.COMPLETE: [CycleState.IDLE],
        CycleState.ERROR: [CycleState.IDLE],
    }

    def __init__(self):
        self.state = CycleState.IDLE
        self.context: dict = {}
        self._history: list[tuple[CycleState, CycleState]] = []

    def transition(self, new_state: CycleState) -> bool:
        """Выполнить переход в новое состояние."""
        allowed = self.TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            logger.warning(
                f"Invalid transition: {self.state.value} -> {new_state.value}"
            )
            return False

        self._history.append((self.state, new_state))
        logger.info(f"FSM: {self.state.value} -> {new_state.value}")
        self.state = new_state
        return True

    def set_context(self, key: str, value):
        """Установить контекст цикла."""
        self.context[key] = value

    def get_context(self, key: str, default=None):
        """Получить значение контекста."""
        return self.context.get(key, default)

    def reset(self):
        """Сброс автомата."""
        self.state = CycleState.IDLE
        self.context.clear()
        self._history.clear()

    @property
    def is_complete(self) -> bool:
        return self.state == CycleState.COMPLETE

    @property
    def is_error(self) -> bool:
        return self.state == CycleState.ERROR

    @property
    def history(self) -> list[tuple[str, str]]:
        return [(s.value, n.value) for s, n in self._history]
