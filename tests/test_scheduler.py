"""Tests for TradingScheduler."""
from unittest.mock import MagicMock


def test_scheduler_start_stop(paper_config):
    from tools.scheduler import TradingScheduler
    supervisor = MagicMock()
    supervisor.run_trading_cycle.return_value = {"orders_placed": 0, "errors": []}
    scheduler = TradingScheduler(supervisor, config=paper_config)

    scheduler.start()
    import time
    time.sleep(0.5)
    status = scheduler.get_status()
    assert status.get("running") is True

    scheduler.stop()
    status = scheduler.get_status()
    assert status.get("running") is False


def test_scheduler_get_logs():
    from tools.memory import get_agent_logs
    logs = get_agent_logs(limit=5)
    assert isinstance(logs, list)
