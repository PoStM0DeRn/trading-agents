"""Mock T-Invest broker client for testing."""


class MockTInvestClient:
    def __init__(self):
        self._connected = True
        self._orders = []

    def ensure_connected(self):
        if not self._connected:
            raise ConnectionError("Not connected")

    def place_order(self, ticker=None, quantity=0, side="BUY", order_type="limit", price_limit=None, paper_trading=False):
        order_id = f"mock_{len(self._orders):06d}"
        self._orders.append({"order_id": order_id, "ticker": ticker, "quantity": quantity, "side": side})
        return {"order_id": order_id, "status": "EXECUTION_REPORT_STATUS_FILL", "filled_price": price_limit or 150.0}

    def get_positions(self) -> list:
        return self._orders

    def close(self):
        pass
