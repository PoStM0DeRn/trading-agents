"""Service health monitoring for graceful degradation with alerts."""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from tools.memory import get_db_path

logger = logging.getLogger(__name__)

SERVICE_NAMES = {"llm": "LLM", "broker": "Broker", "db": "Database"}


@dataclass
class ServiceHealth:
    llm_available: bool = False
    broker_available: bool = False
    db_available: bool = False
    last_check: Optional[datetime] = None
    consecutive_failures: dict[str, int] = field(default_factory=lambda: {"llm": 0, "broker": 0, "db": 0})
    max_consecutive_skips: int = 3
    _prev_available: dict[str, bool] = field(default_factory=lambda: {"llm": True, "broker": True, "db": True})

    def _check_transition(self, service: str, current: bool) -> None:
        """Send alert on service state transitions (up→down or down→up).

        Args:
            service: Service name ('llm', 'broker', 'db').
            current: Current availability state.

        """
        prev = self._prev_available.get(service, True)
        if prev and not current:
            from tools.service import send_alert
            send_alert(
                f"SERVICE DOWN: {SERVICE_NAMES.get(service, service)} became unavailable "
                f"(failures: {self.consecutive_failures.get(service, 0)})",
                severity="warning",
            )
        elif not prev and current:
            from tools.service import send_alert
            send_alert(
                f"SERVICE RECOVERED: {SERVICE_NAMES.get(service, service)} is back online",
                severity="info",
            )
        self._prev_available[service] = current

    def check_llm(self, llm_client: Any) -> bool:
        """Check LLM availability by pinging the client.

        Args:
            llm_client: The LLM client instance to check.

        Returns:
            bool: True if LLM is available, False otherwise.

        """
        try:
            available = llm_client.is_available()
            self.llm_available = available
            if available:
                self.consecutive_failures["llm"] = 0
            else:
                self.consecutive_failures["llm"] += 1
            self._check_transition("llm", available)
        except Exception as e:
            self.llm_available = False
            self.consecutive_failures["llm"] += 1
            self._check_transition("llm", False)
            logger.warning(f"LLM health check failed: {e}")
        return self.llm_available

    def check_broker(self, tinvest_client: Any) -> bool:
        """Check broker API connectivity.

        Args:
            tinvest_client: The T-Invest client instance.

        Returns:
            bool: True if broker is available, False otherwise.

        """
        try:
            tinvest_client.ensure_connected()
            self.broker_available = tinvest_client._connected
            if self.broker_available:
                self.consecutive_failures["broker"] = 0
            else:
                self.consecutive_failures["broker"] += 1
            self._check_transition("broker", self.broker_available)
        except Exception as e:
            self.broker_available = False
            self.consecutive_failures["broker"] += 1
            self._check_transition("broker", False)
            logger.warning(f"Broker health check failed: {e}")
        return self.broker_available

    def check_db(self) -> bool:
        """Check SQLite database connectivity with a SELECT 1.

        Returns:
            bool: True if database is reachable, False otherwise.

        """
        try:
            conn = sqlite3.connect(get_db_path())
            conn.execute("SELECT 1")
            conn.close()
            self.db_available = True
            self.consecutive_failures["db"] = 0
            self._check_transition("db", True)
        except Exception as e:
            self.db_available = False
            self.consecutive_failures["db"] += 1
            self._check_transition("db", False)
            logger.warning(f"Database health check failed: {e}")
        return self.db_available

    def check_all(self, llm_client: Any = None, tinvest_client: Any = None) -> dict[str, bool]:
        """Check all configured services and return their status dict.

        Args:
            llm_client: Optional LLM client to check.
            tinvest_client: Optional T-Invest client to check.

        Returns:
            dict[str, bool]: Mapping of service names to their availability.

        """
        results = {}
        if llm_client:
            results["llm"] = self.check_llm(llm_client)
        if tinvest_client:
            results["broker"] = self.check_broker(tinvest_client)
        results["db"] = self.check_db()
        self.last_check = datetime.now(timezone.utc)
        return results

    def should_skip_cycle(self) -> Optional[str]:
        """Return reason to skip cycle if LLM has been down for max_consecutive_skips checks.

        Returns:
            Optional[str]: The skip reason string, or None if cycle should proceed.

        """
        if self.consecutive_failures["llm"] >= self.max_consecutive_skips:
            return f"LLM unavailable for {self.consecutive_failures['llm']} consecutive checks"
        return None

    def can_execute_orders(self) -> bool:
        """Return whether broker is available for order execution.

        Returns:
            bool: True if broker is available and orders can be executed.

        """
        return self.broker_available

    def to_dict(self) -> dict:
        """Serialize health state to a plain dict.

        Returns:
            dict: A dictionary with all health state fields.

        """
        return {
            "llm_available": self.llm_available,
            "broker_available": self.broker_available,
            "db_available": self.db_available,
            "last_check": str(self.last_check) if self.last_check else None,
            "consecutive_failures": dict(self.consecutive_failures),
        }
