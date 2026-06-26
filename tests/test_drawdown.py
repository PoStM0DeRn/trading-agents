"""Tests for drawdown checks."""
from tools.memory import init_db, _query


def _seed_peak(peak_value: float = 100000):
    _query("DELETE FROM equity_snapshots")
    _query("INSERT INTO equity_snapshots (total_value) VALUES (?)", (peak_value,))


def test_drawdown_below_limit(paper_config):
    init_db()
    _seed_peak(100000)
    from tools.drawdown import check_drawdown
    result = check_drawdown(current_equity=97000, config=paper_config)
    assert result["triggered"] is False
    assert result["action"] == "ok"


def test_drawdown_pause(paper_config):
    init_db()
    _seed_peak(100000)
    from tools.drawdown import check_drawdown
    result = check_drawdown(current_equity=93000, config=paper_config)
    assert result["triggered"] is True
    assert result["action"] == "pause"


def test_drawdown_halt(paper_config):
    init_db()
    _seed_peak(100000)
    from tools.drawdown import check_drawdown
    result = check_drawdown(current_equity=82000, config=paper_config)
    assert result["triggered"] is True
    assert result["action"] == "halt"


def test_drawdown_zero_equity(paper_config):
    from tools.drawdown import check_drawdown
    result = check_drawdown(current_equity=0, config=paper_config)
    assert result["drawdown"] == 0
    assert result["action"] == "ok"
