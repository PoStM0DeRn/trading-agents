"""Shared fixtures and mocks for all tests."""

import sys
from pathlib import Path

import pytest

from tests.mocks.mock_llm import MockLLMClient
from tests.mocks.mock_broker import MockTInvestClient

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Paper config ──


@pytest.fixture
def paper_config() -> dict:
    return {
        "trading": {
            "paper_trading": True,
            "max_daily_loss_percent": 2.0,
            "max_daily_drawdown": 5.0,
            "max_total_drawdown": 15.0,
            "max_leverage": 3.0,
            "max_position_percent": 20.0,
            "retention_days": 90,
        },
        "llm": {"model": "test-model"},
    }


@pytest.fixture
def mock_llm():
    return MockLLMClient()


@pytest.fixture
def mock_tinvest():
    return MockTInvestClient()
