"""Tests for paper trading mode."""
from tests.conftest import MockLLMClient, MockTInvestClient


def test_paper_trading_creates_supervisor(paper_config):
    from agents.supervisor import SupervisorAgent
    llm = MockLLMClient()
    supervisor = SupervisorAgent(llm, config=paper_config)
    assert supervisor.paper_trading is True
    assert supervisor.execution_agent.paper_trading is True


def test_paper_execution_does_not_call_broker(paper_config):
    from agents.execution_agent import ExecutionAgent
    from tools.execution import set_client
    llm = MockLLMClient()
    tinvest = MockTInvestClient()
    set_client(tinvest)
    agent = ExecutionAgent(llm, paper_trading=True)
    result = agent._call_tool("place_order", ticker="SBER", quantity=10, side="BUY", order_type="market", paper_trading=True)
    assert result["status"] == "paper"
    assert result["order_id"].startswith("paper_")
