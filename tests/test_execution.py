"""Tests for execution module."""
from tests.conftest import MockTInvestClient


def _setup():
    from tools.execution import set_client, place_order
    set_client(MockTInvestClient())
    return place_order


def test_idempotency_key_uniqueness():
    from tools.execution import _idempotency_key
    key1 = _idempotency_key("SBER", 10, "BUY", 250.0)
    key2 = _idempotency_key("SBER", 10, "BUY", 250.0)
    assert key1 == key2


def test_idempotency_key_different():
    from tools.execution import _idempotency_key
    key1 = _idempotency_key("SBER", 10, "BUY", 250.0)
    key2 = _idempotency_key("GAZP", 10, "BUY", 250.0)
    assert key1 != key2


def test_place_order_paper_mode():
    place_order = _setup()
    result = place_order("SBER", 10, side="BUY", order_type="market", paper_trading=True)
    assert result["status"] == "paper"
    assert result["order_id"].startswith("paper_")


def test_place_order_invalid_quantity():
    place_order = _setup()
    import pytest
    with pytest.raises(ValueError, match="must be positive"):
        place_order("SBER", 0, side="BUY", order_type="market", paper_trading=True)


def test_place_order_invalid_side():
    place_order = _setup()
    import pytest
    with pytest.raises(ValueError, match="Side must be"):
        place_order("SBER", 10, side="INVALID", order_type="market", paper_trading=True)


def test_place_order_limit_missing_price():
    place_order = _setup()
    import pytest
    with pytest.raises(ValueError, match="Price limit"):
        place_order("SBER", 10, order_type="limit", side="BUY", paper_trading=True)
