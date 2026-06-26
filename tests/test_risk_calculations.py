"""Tests for risk calculations."""


def test_position_size_long():
    from tools.risk_calculations import calculate_position_size_long
    qty = calculate_position_size_long(
        capital=100000, risk_percent=1.0,
        entry_price=150.0, stop_loss_price=145.0,
    )
    assert qty == 200


def test_position_size_short():
    from tools.risk_calculations import calculate_position_size_short
    qty = calculate_position_size_short(
        capital=100000, risk_percent=1.0,
        entry_price=150.0, stop_loss_price=155.0,
        borrow_rate_annual=0.0,
    )
    assert qty == 200


def test_position_size_short_with_borrow():
    from tools.risk_calculations import calculate_position_size_short
    qty = calculate_position_size_short(
        capital=100000, risk_percent=1.0,
        entry_price=150.0, stop_loss_price=155.0,
        borrow_rate_annual=10.0, expected_hold_days=30,
    )
    assert qty < 200


def test_commission():
    from tools.risk_calculations import calculate_total_commission
    result = calculate_total_commission(ticker="AAPL", quantity=100, price=150, side="BUY")
    assert result["commission_amount"] > 0


def test_entry_below_stop_raises():
    from tools.risk_calculations import calculate_position_size_long
    import pytest
    with pytest.raises(ValueError):
        calculate_position_size_long(capital=100000, risk_percent=1.0, entry_price=100, stop_loss_price=110)


def test_short_entry_above_stop_raises():
    from tools.risk_calculations import calculate_position_size_short
    import pytest
    with pytest.raises(ValueError):
        calculate_position_size_short(capital=100000, risk_percent=1.0, entry_price=150, stop_loss_price=140)
