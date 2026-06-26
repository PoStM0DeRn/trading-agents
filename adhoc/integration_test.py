"""Integration test to verify the full trading pipeline works."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from unittest.mock import patch, MagicMock
from integrations.lmstudio_client import LMStudioClient
from agents.risk_manager import RiskManagerAgent
from agents.portfolio_manager import PortfolioManagerAgent

def mock_get_current_quote(ticker):
    """Mock quote that returns valid prices."""
    return {"last": 250.0, "ask": 250.5, "bid": 249.5, "volume": 1000000}

def test_risk_manager_position_capping():
    """Test that Risk Manager properly caps position size."""
    logger.info("=== Testing Risk Manager Position Capping ===")
    
    llm = LMStudioClient()
    
    with patch('tools.market_data.get_current_quote', side_effect=mock_get_current_quote):
        rm = RiskManagerAgent(llm, config={
            "risk": {"default_risk_per_trade": 1.0},
            "trading": {
                "default_leverage": 3.0,
                "max_leverage": 3.0,
                "max_position_percent": 20.0  # 20% limit
            }
        })
        
        # Mock the tool call for position size calculation
        # This simulates what calculate_position_size_leveraged would return
        mock_result = {
            "quantity": 500,  # This would be 125% of capital
            "total_cost": 125000,
            "own_required": 41667,
            "borrowed": 83333
        }
        
        with patch.object(rm, '_call_tool', return_value=mock_result):
            proposal = {
                "id": "test-123",
                "ticker": "SBER",
                "action": "LONG_OPEN",
                "confidence": 0.8,
                "rationale": "Test trade",
                "suggested_stop_loss": 240.0,
                "suggested_take_profit": 270.0,
                "strategy": "trend"
            }
            
            result = rm.process({
                "proposal": proposal,
                "verdict": {},
                "capital": 100000.0,
                "current_positions": []
            })
            
            logger.info(f"  Result status: {result.get('status')}")
            
            if result.get('status') == 'approved':
                qty = result.get('quantity', 0)
                position_value = qty * 250.0
                max_allowed = 100000.0 * 0.20
                
                logger.info(f"  Original quantity: 500")
                logger.info(f"  Capped quantity: {qty}")
                logger.info(f"  Position value: {position_value:.2f} RUB")
                logger.info(f"  Max allowed (20%): {max_allowed:.2f} RUB")
                
                if qty < 500:
                    logger.info("  Position was capped correctly")
                else:
                    logger.error("  FAIL: Position was not capped!")
                    return False
                    
                if position_value <= max_allowed * 1.1:
                    logger.info("  Position within limits")
                else:
                    logger.error("  FAIL: Position exceeds limit!")
                    return False
            else:
                logger.info(f"  Rejection reason: {result.get('reason', 'unknown')}")
                # Check if it's a valid rejection
                if "Position too small" in str(result.get('reason', '')):
                    logger.info("  (Valid rejection - position would be too small)")
                else:
                    logger.warning("  UNEXPECTED REJECTION")
                    return False
        
        logger.info("Risk Manager capping OK\n")
        return True

def test_portfolio_manager_with_capped_order():
    """Test that Portfolio Manager approves properly capped orders."""
    logger.info("=== Testing Portfolio Manager with Capped Order ===")
    
    llm = LMStudioClient()
    pm = PortfolioManagerAgent(llm, config={
        "trading": {
            "max_positions": 10,
            "max_position_percent": 20.0,
            "max_sector_exposure": 40.0,
            "max_short_exposure": 20.0
        }
    }, paper_trading=True)
    
    # Order that's within limits (capped by Risk Manager)
    order = {
        "proposal_id": "test-456",
        "ticker": "SBER",
        "action": "LONG_OPEN",
        "quantity": 80,  # 80 * 250 = 20000 RUB = 20% of 100000
        "entry_price_limit": 250.0
    }
    
    result = pm.process({
        "order": order,
        "current_positions": [],
        "portfolio_value": 100000.0
    })
    
    logger.info(f"  Status: {result.get('status')}")
    logger.info(f"  Order percent: {result.get('portfolio_metrics', {}).get('order_percent', 0):.1f}%")
    logger.info(f"  Max allowed: 20.0%")
    
    if result.get('status') == 'Approved':
        logger.info("  Order Approved - within limits")
        logger.info("Portfolio Manager OK\n")
        return True
    else:
        logger.error(f"  FAIL: Order rejected: {result.get('rationale', 'unknown')}")
        return False

def test_full_pipeline_simulation():
    """Simulate the full pipeline from proposal to approval."""
    logger.info("=== Testing Full Pipeline Simulation ===")
    
    llm = LMStudioClient()
    
    with patch('tools.market_data.get_current_quote', side_effect=mock_get_current_quote):
        # Risk Manager
        rm = RiskManagerAgent(llm, config={
            "risk": {"default_risk_per_trade": 1.0},
            "trading": {
                "default_leverage": 3.0,
                "max_leverage": 3.0,
                "max_position_percent": 20.0
            }
        })
        
        # Mock position size calculation to return reasonable size
        mock_result = {
            "quantity": 80,
            "total_cost": 20000,
            "own_required": 6667,
            "borrowed": 13333
        }
        
        with patch.object(rm, '_call_tool', return_value=mock_result):
            proposal = {
                "id": "test-789",
                "ticker": "SBER",
                "action": "LONG_OPEN",
                "confidence": 0.8,
                "rationale": "Test trade",
                "suggested_stop_loss": 240.0,
                "suggested_take_profit": 270.0,
                "strategy": "trend"
            }
            
            risk_result = rm.process({
                "proposal": proposal,
                "verdict": {},
                "capital": 100000.0,
                "current_positions": []
            })
            
            logger.info(f"  Risk Manager: {risk_result.get('status')}")
            
            if risk_result.get('status') != 'approved':
                logger.error(f"  FAIL: Risk Manager rejected: {risk_result.get('reason', 'unknown')}")
                return False
            
            # Portfolio Manager
            pm = PortfolioManagerAgent(llm, config={
                "trading": {
                    "max_positions": 10,
                    "max_position_percent": 20.0,
                    "max_sector_exposure": 40.0,
                    "max_short_exposure": 20.0
                }
            }, paper_trading=True)
            
            portfolio_result = pm.process({
                "order": risk_result,
                "current_positions": [],
                "portfolio_value": 100000.0
            })
            
            logger.info(f"  Portfolio Manager: {portfolio_result.get('status')}")
            
            if portfolio_result.get('status') == 'Approved':
                logger.info("  Full pipeline PASSED - order would be executed")
                logger.info("Full Pipeline Simulation OK\n")
                return True
            else:
                logger.error(f"  FAIL: Portfolio Manager rejected: {portfolio_result.get('rationale', 'unknown')}")
                return False

if __name__ == "__main__":
    logger.info("Running integration tests...\n")
    
    all_passed = True
    all_passed &= test_risk_manager_position_capping()
    all_passed &= test_portfolio_manager_with_capped_order()
    all_passed &= test_full_pipeline_simulation()
    
    if all_passed:
        logger.info("=== ALL INTEGRATION TESTS PASSED ===")
        logger.info("\nSummary of fixes verified:")
        logger.info("  1. Risk Manager caps position to max_position_percent")
        logger.info("  2. Portfolio Manager approves properly capped orders")
        logger.info("  3. Full pipeline: Proposal -> Risk -> Portfolio -> Approved")
        sys.exit(0)
    else:
        logger.error("=== SOME INTEGRATION TESTS FAILED ===")
        sys.exit(1)
