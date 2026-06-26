import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from config.secrets import secrets

import grpc
from tinkoff.invest import Client
from tinkoff.invest.schemas import CandleInterval

from tools.retry import retry

logger = logging.getLogger(__name__)

_figi_cache: dict[str, str] = {}

MOEX_FIGI = {
    "SBER": "BBG004730N88",
    "GAZP": "BBG004730RP0",
    "LKOH": "BBG004731032",
    "GMKN": "BBG004731489",
    "YDEX": "TCS00A107T19",
    "VTBR": "BBG004730ZJ9",
    "ROSN": "BBG004731354",
    "NVTK": "BBG00475KKY8",
    "SBERP": "BBG0047315Y7",
}


def _quotation_to_float(q) -> float:
    return q.units + q.nano / 1e9


def _float_to_quotation(val):
    from tinkoff.invest.schemas import Quotation
    units = int(val)
    nano = int((val - units) * 1e9)
    return Quotation(units=units, nano=nano)


class TInvestClient:
    """T-Invest gRPC client for MOEX with auto-reconnection."""

    def __init__(self, token: Optional[str] = None, account_id: Optional[str] = None):
        self.token = token or secrets.TINVEST_TOKEN
        self.account_id = account_id or secrets.TINVEST_ACCOUNT_ID
        self._channel = None
        self._instruments = None
        self._market_data = None
        self._operations = None
        self._orders = None
        self._portfolio = None
        self._connected = False

    def connect(self):
        self.close()
        if not self.token:
            raise RuntimeError("T-Invest token not configured")
        self._channel = Client(token=self.token)
        services = self._channel.__enter__()
        self._instruments = services.instruments
        self._market_data = services.market_data
        self._operations = services.operations
        self._orders = services.orders
        self._connected = True
        return self

    def close(self):
        if self._channel is not None:
            try:
                self._channel.__exit__(None, None, None)
            except Exception:
                pass
            self._channel = None
        self._connected = False

    def ensure_connected(self):
        """Проверить соединение и переподключиться при необходимости."""
        if not self.token:
            return
        if self._connected and self._channel is not None:
            try:
                self._instruments.find_instrument(query="SBER")
                return
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.warning(f"gRPC channel unavailable: {e.details()}")
                else:
                    raise
            except Exception as e:
                logger.warning(f"Connection check failed: {e}")
            self._connected = False

        for attempt in range(3):
            try:
                logger.info(f"Reconnecting to T-Invest (attempt {attempt + 1}/3)...")
                self.connect()
                logger.info("T-Invest reconnected.")
                return
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(1 + attempt)

        logger.error("T-Invest reconnection failed after 3 attempts")

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.close()

    @retry(max_retries=2, base_delay=0.5, exceptions=(grpc.RpcError,))
    def _resolve_figi(self, ticker: str) -> str:
        ticker_upper = ticker.upper()
        if ticker_upper in MOEX_FIGI:
            return MOEX_FIGI[ticker_upper]
        if ticker_upper in _figi_cache:
            return _figi_cache[ticker_upper]

        search = self._instruments.find_instrument(query=ticker_upper)
        for inst in search.instruments:
            if inst.ticker == ticker_upper and inst.class_code == "TQBR":
                _figi_cache[ticker_upper] = inst.figi
                return inst.figi

        if search.instruments:
            figi = search.instruments[0].figi
            _figi_cache[ticker_upper] = figi
            return figi

        raise ValueError(f"Ticker {ticker_upper} not found")

    def get_quote(self, ticker: str) -> dict:
        figi = self._resolve_figi(ticker)
        prices = self._market_data.get_last_prices(figi=[figi])
        last_price = 0.0
        for p in prices.last_prices:
            last_price = _quotation_to_float(p.price)

        bid = 0.0
        ask = 0.0
        try:
            book = self._market_data.get_order_book(figi=figi, depth=1)
            if book.bids:
                bid = _quotation_to_float(book.bids[0].price)
            if book.asks:
                ask = _quotation_to_float(book.asks[0].price)
        except Exception:
            pass

        return {
            "ticker": ticker.upper(),
            "figi": figi,
            "bid": round(bid, 2),
            "ask": round(ask, 2),
            "last": round(last_price, 2),
            "spread": round(ask - bid, 2) if bid and ask else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @retry(max_retries=2, base_delay=0.5, exceptions=(grpc.RpcError,))
    def get_historical_data(
        self, ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> list[dict]:
        figi = self._resolve_figi(ticker)
        now = datetime.now(timezone.utc)
        from_date = self._parse_period(period, now)

        interval_map = {
            "1m": CandleInterval.CANDLE_INTERVAL_1_MIN,
            "5m": CandleInterval.CANDLE_INTERVAL_5_MIN,
            "15m": CandleInterval.CANDLE_INTERVAL_15_MIN,
            "1h": CandleInterval.CANDLE_INTERVAL_HOUR,
            "1d": CandleInterval.CANDLE_INTERVAL_DAY,
        }
        candle_interval = interval_map.get(interval, CandleInterval.CANDLE_INTERVAL_DAY)

        candles_resp = self._market_data.get_candles(
            figi=figi,
            from_=from_date,
            to=now,
            interval=candle_interval,
        )

        result = []
        for c in candles_resp.candles:
            result.append({
                "time": str(c.time)[:19],
                "open": round(_quotation_to_float(c.open), 2),
                "high": round(_quotation_to_float(c.high), 2),
                "low": round(_quotation_to_float(c.low), 2),
                "close": round(_quotation_to_float(c.close), 2),
                "volume": c.volume,
            })

        return result

    def get_fundamentals(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "pe_ratio": None,
            "note": "Fundamentals not available via gRPC API",
        }

    @retry(max_retries=2, base_delay=0.5, exceptions=(grpc.RpcError,))
    def get_positions(self) -> list[dict]:
        portfolio = self._operations.get_portfolio(account_id=self.account_id)
        result = []
        for pos in portfolio.positions:
            ticker = getattr(pos, 'ticker', '') or ''
            result.append({
                "ticker": ticker,
                "figi": pos.figi,
                "quantity": int(pos.quantity.units) if pos.quantity else 0,
                "average_price": _quotation_to_float(pos.average_position_price) if pos.average_position_price else 0,
                "current_price": _quotation_to_float(pos.current_price) if pos.current_price else 0,
                "pnl": _quotation_to_float(pos.expected_yield) if pos.expected_yield else 0,
                "currency": "RUB",
            })
        return result

    @retry(max_retries=2, base_delay=0.5, exceptions=(grpc.RpcError,))
    def get_account_balance(self) -> dict:
        portfolio = self._operations.get_portfolio(account_id=self.account_id)
        total = 0.0
        if hasattr(portfolio, 'total_amount_portfolio') and portfolio.total_amount_portfolio:
            total = _quotation_to_float(portfolio.total_amount_portfolio)
        return {
            "total": round(total, 2),
            "currency": "RUB",
            "positions_count": len(portfolio.positions),
        }

    @retry(max_retries=2, base_delay=0.5, exceptions=(grpc.RpcError,))
    def place_order(
        self,
        ticker: str,
        quantity: int,
        side: str,
        order_type: str = "limit",
        price_limit: Optional[float] = None,
    ) -> dict:
        from tinkoff.invest.schemas import OrderDirection, OrderType

        figi = self._resolve_figi(ticker)
        direction = OrderDirection.ORDER_DIRECTION_BUY if side == "BUY" else OrderDirection.ORDER_DIRECTION_SELL
        price = _float_to_quotation(price_limit) if price_limit else None
        order_type_enum = OrderType.ORDER_TYPE_MARKET if order_type == "market" else OrderType.ORDER_TYPE_LIMIT

        response = self._orders.post_order(
            account_id=self.account_id,
            figi=figi,
            quantity=quantity,
            direction=direction,
            order_type=order_type_enum,
            price=price,
        )

        return {
            "order_id": response.order_id,
            "status": response.execution_report_status.name,
            "ticker": ticker,
            "quantity": quantity,
            "side": side,
            "filled_price": price_limit,
        }

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._orders.cancel_order(account_id=self.account_id, order_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_order_status(self, order_id: str) -> dict:
        orders = self._orders.get_orders(account_id=self.account_id)
        for order in orders.orders:
            if order.order_id == order_id:
                return {
                    "order_id": order_id,
                    "status": order.execution_report_status.name,
                    "filled_quantity": order.lots_executed,
                    "price": _quotation_to_float(order.price) if order.price else 0,
                }
        return {"order_id": order_id, "status": "NOT_FOUND"}

    def _parse_period(self, period: str, now: datetime) -> datetime:
        units = {"d": "days", "w": "weeks", "mo": "months", "y": "years"}
        for suffix, unit in units.items():
            if period.endswith(suffix):
                value = int(period[: -len(suffix)])
                if unit == "months":
                    return now - timedelta(days=value * 30)
                elif unit == "years":
                    return now - timedelta(days=value * 365)
                else:
                    return now - timedelta(**{unit: value})
        return now - timedelta(days=30)
