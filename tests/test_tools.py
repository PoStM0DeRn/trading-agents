"""Base tests for tools module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.risk_calculations import (
    calculate_position_size_long,
    calculate_position_size_short,
    calculate_total_commission,
    calculate_cycle_commission,
)
from tools.market_data import _calc_rsi, _calc_sma, _calc_bollinger_full as _calc_bollinger
from tools.validator import validate_ticker
import numpy as np
import pandas as pd
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_position_size_long():
    qty = calculate_position_size_long(
        capital=100000,
        risk_percent=1.0,
        entry_price=150.0,
        stop_loss_price=145.0,
    )
    assert qty == 200, f"Expected 200, got {qty}"
    logger.info("[OK] Position size LONG")


def test_position_size_short():
    qty = calculate_position_size_short(
        capital=100000,
        risk_percent=1.0,
        entry_price=150.0,
        stop_loss_price=155.0,
        borrow_rate_annual=0.0,
    )
    assert qty == 200, f"Expected 200, got {qty}"
    logger.info("[OK] Position size SHORT")


def test_position_size_short_with_borrow():
    qty = calculate_position_size_short(
        capital=100000,
        risk_percent=1.0,
        entry_price=150.0,
        stop_loss_price=155.0,
        borrow_rate_annual=10.0,
        expected_hold_days=30,
    )
    assert qty < 200, f"Expected <200 due to borrow cost, got {qty}"
    logger.info(f"[OK] Position size SHORT with borrow (qty={qty})")


def test_commission():
    comm = calculate_total_commission(
        ticker="AAPL",
        quantity=100,
        price=150.0,
        side="BUY",
    )
    assert comm["commission_amount"] > 0, "Commission should be > 0"
    logger.info(f"[OK] Commission ({comm['commission_amount']})")


def test_cycle_commission():
    cycle = calculate_cycle_commission(
        ticker="AAPL",
        quantity=100,
        entry_price=150.0,
        exit_price=155.0,
        side="LONG_OPEN",
    )
    assert cycle["total_commission"] > 0, "Cycle commission should be > 0"
    logger.info(f"[OK] Cycle commission ({cycle['total_commission']})")


def test_rsi():
    prices = pd.Series([100 + i * 0.5 + np.random.randn() for i in range(30)])
    rsi = _calc_rsi(prices)
    assert 0 <= rsi <= 100, f"RSI should be 0-100, got {rsi}"
    logger.info(f"[OK] RSI ({rsi})")


def test_sma():
    prices = pd.Series([100 + i for i in range(50)])
    sma = _calc_sma(prices, 20)
    assert sma > 0, f"SMA should be > 0, got {sma}"
    logger.info(f"[OK] SMA ({sma})")


def test_bollinger():
    prices = pd.Series([100 + np.random.randn() for _ in range(30)])
    bb = _calc_bollinger(prices)
    assert bb["upper"] > bb["middle"] > bb["lower"], f"BB order wrong: {bb}"
    logger.info(f"[OK] Bollinger Bands ({bb['upper']}/{bb['middle']}/{bb['lower']})")


def test_validate_ticker():
    assert validate_ticker("SBER") == "SBER"
    assert validate_ticker("GAZP") == "GAZP"
    for t in ("INVALID_TICKER", "", "TOOLONG"):
        try:
            validate_ticker(t)
            assert False, f"Expected ValueError for {t!r}"
        except ValueError:
            pass
    # "A" is valid format (1-5 chars) but unknown — logs warning, returns uppercase
    assert validate_ticker("a") == "A"
    logger.info("[OK] Ticker validation")


def test_errors():
    try:
        calculate_position_size_long(
            capital=100000,
            risk_percent=1.0,
            entry_price=150.0,
            stop_loss_price=155.0,
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        logger.info("[OK] Error handling")


if __name__ == "__main__":
    logger.info("Running tests...\n")

    test_position_size_long()
    test_position_size_short()
    test_position_size_short_with_borrow()
    test_commission()
    test_cycle_commission()
    test_rsi()
    test_sma()
    test_bollinger()
    test_validate_ticker()
    test_errors()

    logger.info("\nAll tests passed!")
