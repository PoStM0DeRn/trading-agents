"""Tests for RiskManagerAgent."""
from tests.conftest import MockLLMClient


def test_risk_manager_initialization(paper_config):
    from agents.risk_manager import RiskManagerAgent
    llm = MockLLMClient()
    rm = RiskManagerAgent(llm, config=paper_config)
    assert rm.name == "RiskManager"


def test_risk_manager_daily_loss_check(paper_config):
    from agents.risk_manager import RiskManagerAgent
    from unittest.mock import patch
    llm = MockLLMClient()
    rm = RiskManagerAgent(llm, config=paper_config)
    with patch.object(rm, '_call_tool', return_value={"commission_amount": 10, "commission_percent": 0.05}):
        result = rm._check_daily_loss_limit()
        assert isinstance(result, dict)
