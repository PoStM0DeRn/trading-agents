"""Тест оптимизированных комплексных индикаторов: Ichimoku, Fibonacci, ADX."""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from tools.advanced_analysis import (
    get_ichimoku,
    get_fibonacci_levels,
    get_adx,
    get_advanced_snapshot,
    set_client,
)
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MockClient:
    """Мок клиента для тестирования."""

    def __init__(self):
        np.random.seed(42)
        n = 200
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="D")
        base_price = 250.0
        returns = np.random.normal(0.0005, 0.02, n)
        prices = base_price * np.exp(np.cumsum(returns))

        self._data = pd.DataFrame({
            "time": dates,
            "open": prices * (1 + np.random.uniform(-0.01, 0.01, n)),
            "high": prices * (1 + np.random.uniform(0, 0.02, n)),
            "low": prices * (1 - np.random.uniform(0, 0.02, n)),
            "close": prices,
            "volume": np.random.randint(100000, 1000000, n),
        })

    def get_historical_data(self, ticker, period, interval):
        return self._data.to_dict("records")


def test_all():
    logger.info("=" * 70)
    logger.info("  ТЕСТ ОПТИМИЗИРОВАННЫХ ИНДИКАТОВ")
    logger.info("  Ichimoku + Fibonacci + ADX")
    logger.info("=" * 70)

    client = MockClient()
    set_client(client)

    ticker = "SBER"

    # 1. Ichimoku
    logger.info("\n[1] Ichimoku Cloud:")
    result = get_ichimoku(ticker, "6mo")
    if "error" not in result:
        logger.info(f"  Tenkan: {result['tenkan']}, Kijun: {result['kijun']}")
        logger.info(f"  Cloud: {result['cloud_bottom']} - {result['cloud_top']}")
        logger.info(f"  Trend: {result['trend']}, TK Cross: {result['tk_cross']}")
        logger.info(f"  Price vs Cloud: {result['price_vs_cloud']}")
    else:
        logger.info(f"  ERROR: {result['error']}")

    # 2. Fibonacci
    logger.info("\n[2] Fibonacci Retracement:")
    result = get_fibonacci_levels(ticker, "3mo")
    if "error" not in result:
        logger.info(f"  Swing: {result['swing_low']} - {result['swing_high']}")
        logger.info(f"  Levels: {json.dumps(result['levels'], indent=4)}")
        logger.info(f"  Closest: {result['closest_level']} ({result['closest_level_price']})")
        logger.info(f"  Trend: {result['trend']}")
    else:
        logger.info(f"  ERROR: {result['error']}")

    # 3. ADX
    logger.info("\n[3] ADX:")
    result = get_adx(ticker, "3mo")
    if "error" not in result:
        logger.info(f"  ADX: {result['adx']}")
        logger.info(f"  +DI: {result['plus_di']}, -DI: {result['minus_di']}")
        logger.info(f"  Strength: {result['trend_strength']}, Direction: {result['trend_direction']}")
        logger.info(f"  Signal: {result['signal']}")
    else:
        logger.info(f"  ERROR: {result['error']}")

    # 4. Full snapshot
    logger.info("\n[4] Advanced Snapshot:")
    snapshot = get_advanced_snapshot(ticker, "3mo")
    for name, data in snapshot.items():
        status = "OK" if "error" not in data else f"ERROR: {data['error']}"
        logger.info(f"  {name}: {status}")

    logger.info("\n" + "=" * 70)
    logger.info("  ТЕСТ ЗАВЕРШЁН")
    logger.info("  Оптимизация: 26 -> 16 индикаторов (-38%)")
    logger.info("=" * 70)


if __name__ == "__main__":
    test_all()
