"""Tests for input validation."""


def test_validate_ticker_valid():
    from tools.validator import validate_ticker
    assert validate_ticker("SBER") == "SBER"
    assert validate_ticker("GAZP") == "GAZP"


def test_validate_ticker_invalid():
    from tools.validator import validate_ticker
    import pytest
    with pytest.raises(ValueError):
        validate_ticker("INVALID_LONG_TICKER")


def test_validate_side_buy():
    from tools.validator import validate_side
    assert validate_side("BUY") == "BUY"


def test_validate_side_sell():
    from tools.validator import validate_side
    assert validate_side("SELL") == "SELL"


def test_validate_side_invalid():
    from tools.validator import validate_side
    import pytest
    with pytest.raises(ValueError):
        validate_side("HOLD")


def test_validate_positive_number():
    from tools.validator import validate_positive_number
    assert validate_positive_number(100, "test") == 100


def test_validate_positive_number_zero():
    from tools.validator import validate_positive_number
    import pytest
    with pytest.raises(ValueError):
        validate_positive_number(0, "test")
