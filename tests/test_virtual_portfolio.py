"""Tests for virtual portfolio."""
import uuid
from tools.memory import init_db


def test_open_and_close_position():
    import os
    test_db = "data/test_virtual.db"
    os.makedirs("data", exist_ok=True)
    if os.path.exists(test_db):
        os.remove(test_db)

    init_db(test_db)
    from tools.virtual_portfolio import open_position, close_position

    trade_id = f"test_trade_{uuid.uuid4().hex[:8]}"

    result = open_position("SBER", "LONG", 10, 250.0, stop_loss=240.0, take_profit=270.0,
                           trade_id=trade_id)
    assert result["status"] == "filled"

    close_result = close_position(trade_id, close_price=260.0)
    assert close_result["status"] == "closed"

    if os.path.exists(test_db):
        os.remove(test_db)


def test_virtual_balance():
    import os
    test_db = "data/test_virtual_bal.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    init_db(test_db)
    from tools.virtual_portfolio import get_balance
    bal = get_balance()
    assert bal["initial_capital"] == 100000
    assert bal["current_balance"] == 100000

    if os.path.exists(test_db):
        os.remove(test_db)
