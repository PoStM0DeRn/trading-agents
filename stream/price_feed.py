"""Price feed — background polling for live prices."""

import time
import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class PriceFeed:
    """Фоновый опрос цен через T-Invest API."""

    def __init__(
        self,
        tickers: list[str],
        interval: float = 5.0,
        on_update: Optional[Callable] = None,
    ):
        self.tickers = tickers
        self.interval = interval
        self.on_update = on_update
        self._prices: dict[str, dict] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Запуск фонового опроса."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"Price feed started for {self.tickers} (interval={self.interval}s)")

    def stop(self):
        """Остановка опроса."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Price feed stopped")

    def _poll_loop(self):
        """Цикл опроса цен."""
        while self._running:
            try:
                self._fetch_prices()
                if self.on_update:
                    self.on_update(self._prices)
            except Exception as e:
                logger.error(f"Price fetch error: {e}")
            time.sleep(self.interval)

    def _fetch_prices(self):
        """Получить цены для всех тикеров."""
        try:
            # Используем глобальный клиент (инжектируется через main.py)
            from tools import market_data
            if not hasattr(market_data, '_client') or market_data._client is None:
                return

            for ticker in self.tickers:
                try:
                    quote = market_data.get_current_quote(ticker)
                    if quote:
                        self._prices[ticker] = {
                            "last": quote.get("last", 0),
                            "bid": quote.get("bid", 0),
                            "ask": quote.get("ask", 0),
                            "spread": quote.get("spread", 0),
                            "timestamp": time.time(),
                        }
                except Exception as e:
                    logger.debug(f"Price fetch failed for {ticker}: {e}")

        except Exception as e:
            logger.error(f"Price feed init error: {e}")

    def get_prices(self) -> dict:
        """Получить текущие цены."""
        return self._prices.copy()

    def get_price(self, ticker: str) -> Optional[dict]:
        """Получить цену конкретного тикера."""
        return self._prices.get(ticker)
