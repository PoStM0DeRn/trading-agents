"""Corporate events — dividends, earnings, splits."""

import logging

logger = logging.getLogger(__name__)

_client = None


def set_client(client):
    global _client
    _client = client


def _ensure_client() -> bool:
    if _client is None:
        return False
    try:
        _client.ensure_connected()
        return True
    except Exception:
        return False


def get_dividend_calendar(ticker: str) -> dict:
    """Get instrument info with dividend data."""
    if not _ensure_client():
        return {"ticker": ticker, "error": "client_not_connected"}
    try:
        figi = _client._resolve_figi(ticker)

        try:
            from tinkoff.invest.schemas import InstrumentIdType
            response = _client._instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi,
            )
            instrument = response.instrument

            info = {
                "ticker": ticker,
                "figi": figi,
                "name": getattr(instrument, 'name', ''),
                "isin": getattr(instrument, 'isin', ''),
                "lot": getattr(instrument, 'lot', 1),
                "currency": getattr(instrument, 'currency', 'RUB'),
                "instrument_type": getattr(instrument, 'instrument_type', ''),
            }

            # Min price increment
            if hasattr(instrument, 'min_price_increment') and instrument.min_price_increment:
                q = instrument.min_price_increment
                info["min_price_increment"] = q.units + q.nano / 1e9

            return info

        except Exception as e:
            logger.warning(f"Failed to get instrument info for {ticker}: {e}")
            return {"ticker": ticker, "figi": figi, "error": str(e)}
    except Exception as e:
        logger.warning(f"Failed to resolve FIGI for {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}


def get_instrument_info(ticker: str) -> dict:
    """Alias for get_dividend_calendar."""
    return get_dividend_calendar(ticker)


def get_trading_status(ticker: str) -> dict:
    """Check if the instrument is currently tradeable."""
    if not _ensure_client():
        return {"ticker": ticker, "tradeable": False, "error": "client_not_connected"}
    try:
        quote = _client.get_quote(ticker)
        return {
            "ticker": ticker,
            "tradeable": quote.get("last", 0) > 0,
            "last_price": quote.get("last", 0),
            "bid": quote.get("bid", 0),
            "ask": quote.get("ask", 0),
        }
    except Exception as e:
        return {
            "ticker": ticker,
            "tradeable": False,
            "error": str(e),
        }


def get_market_cap_proxy(ticker: str) -> dict:
    """Estimate relative market cap using price * lot size."""
    info = get_dividend_calendar(ticker)
    if not _ensure_client():
        return {"ticker": ticker, "error": "client_not_connected"}
    quote = _client.get_quote(ticker)

    price = quote.get("last", 0)
    lot = info.get("lot", 1)

    return {
        "ticker": ticker,
        "price": price,
        "lot_size": lot,
        "lot_value": round(price * lot, 2),
        "category": "large" if price * lot > 100000 else "mid" if price * lot > 10000 else "small",
    }
