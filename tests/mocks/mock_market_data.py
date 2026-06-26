"""Mock market data functions for testing."""


def mock_get_current_quote(ticker: str) -> dict:
    quotes = {
        "SBER": {"last": 250.0, "ask": 250.5, "bid": 249.5, "volume": 1000000},
        "GAZP": {"last": 180.0, "ask": 180.3, "bid": 179.8, "volume": 500000},
    }
    return quotes.get(ticker.upper(), {"last": 100.0, "ask": 100.5, "bid": 99.5, "volume": 100000})
