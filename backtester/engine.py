import json
import logging
import sys
import time
from datetime import datetime, timezone

from .config import BacktestConfig
from .historical_data import fetch_all, get_price_at
from .mock_agents import BacktestSupervisor
from .report import BacktestReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class BacktestEngine:
    """Main backtest engine — runs the full pipeline on historical data."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._cycle_results = []
        self._equity_curve = []

    def run(self) -> dict:
        start_time = time.time()
        logger.info(f"\n{'='*60}")
        logger.info(f"BACKTEST ENGINE")
        logger.info(f"{'='*60}")
        logger.info(f"Tickers: {', '.join(self.config.tickers)}")
        logger.info(f"Period: {self.config.period}, Interval: {self.config.interval}")
        logger.info(f"Capital: {self.config.initial_capital:,.0f} RUB")
        logger.info(f"Leverage: x{self.config.max_leverage}")
        logger.info(f"{'='*60}\n")

        # Step 1: Initialize system
        logger.info("[1/5] Initializing system...")
        supervisor, llm_client, tinvest_client = self._init_system()

        # Step 2: Fetch historical data
        logger.info("[2/5] Fetching historical data...")
        all_candles = fetch_all(
            tinvest_client,
            self.config.tickers,
            self.config.period,
            self.config.interval,
        )
        for ticker, candles in all_candles.items():
            logger.info(f"  {ticker}: {len(candles)} candles")

        # Step 3: Determine trading bars
        logger.info("[3/5] Preparing trading schedule...")
        trading_bars = self._get_trading_bars(all_candles)
        total_bars = len(trading_bars)
        logger.info(f"  Trading bars: {total_bars}")

        if total_bars == 0:
            logger.error("ERROR: No trading bars found!")
            return {"error": "no_trading_bars"}

        # Step 4: Run backtest loop
        logger.info(f"[4/5] Running backtest ({total_bars} bars)...")

        from tools import virtual_portfolio
        virtual_portfolio.reset_account(self.config.initial_capital)

        backtest_supervisor = BacktestSupervisor(
            supervisor=supervisor,
            all_candles=all_candles,
            news_cache={},
            config={
                "backtest": {
                    "slippage": {
                        "type": "percent",
                        "percent": 0.05,
                    }
                }
            },
        )

        equity_curve = []
        all_trades = []

        for bar_num, bar_index in enumerate(trading_bars):
            if bar_num % 50 == 0 or bar_num == total_bars - 1:
                pct = (bar_num + 1) / total_bars * 100
                logger.info(f"  Progress: {bar_num+1}/{total_bars} ({pct:.1f}%)")

            current_prices = {}
            for ticker in self.config.tickers:
                candles = all_candles.get(ticker, [])
                price = get_price_at(candles, bar_index)
                if price > 0:
                    current_prices[ticker] = price

            if not current_prices:
                continue

            # Get current positions
            try:
                positions = virtual_portfolio.get_positions()
            except Exception:
                positions = []

            # Get current capital
            try:
                balance_info = virtual_portfolio.get_balance()
                capital = balance_info["current_balance"]
            except Exception:
                capital = self.config.initial_capital

            # Run cycle
            try:
                report = backtest_supervisor.run_cycle(
                    tickers=self.config.tickers,
                    bar_index=bar_index,
                    current_prices=current_prices,
                    capital=capital,
                    positions=positions,
                )
                self._cycle_results.append(report)
            except Exception as e:
                logger.error(f"Cycle failed at bar {bar_index}: {e}")

            # Record equity
            try:
                summary = virtual_portfolio.get_account_summary(current_prices)
                equity_point = {
                    "bar_index": bar_index,
                    "total_value": summary.get("total_value", capital),
                    "balance": summary.get("balance", capital),
                    "positions_value": summary.get("positions_value", 0),
                    "pnl": summary.get("total_pnl", 0),
                    "margin_level": summary.get("margin_level", 0),
                    "positions_count": summary.get("positions_count", 0),
                }
                equity_curve.append(equity_point)
                self._equity_curve.append(equity_point)
            except Exception as e:
                logger.error(f"Equity snapshot failed: {e}")

        # Step 5: Close all remaining positions
        logger.info("[5/5] Closing remaining positions...")
        try:
            positions = virtual_portfolio.get_positions()
            for pos in positions:
                ticker = pos.get("ticker")
                trade_id = pos.get("trade_id")
                if ticker and trade_id:
                    last_price = get_price_at(
                        all_candles.get(ticker, []),
                        trading_bars[-1] if trading_bars else 0,
                    )
                    if last_price > 0:
                        virtual_portfolio.close_position(trade_id, last_price)
                        all_trades.append({
                            "ticker": ticker,
                            "action": "CLOSE",
                            "pnl": pos.get("pnl", 0),
                        })
        except Exception as e:
            logger.error(f"Failed to close positions: {e}")

        # Generate report
        elapsed = time.time() - start_time
        logger.info(f"\nBacktest completed in {elapsed:.1f}s")

        report_gen = BacktestReport(self.config)
        results = report_gen.generate(
            equity_curve=equity_curve,
            cycle_results=self._cycle_results,
            trade_log=backtest_supervisor.get_trade_log(),
            initial_capital=self.config.initial_capital,
        )

        report_gen.save(results)

        return results

    def _init_system(self):
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

        from tools.bootstrap import load_config, init_system
        config = load_config()

        config["trading"]["paper_trading"] = True
        config["trading"]["initial_capital"] = self.config.initial_capital
        config["trading"]["max_leverage"] = self.config.max_leverage
        config["trading"]["default_leverage"] = self.config.default_leverage

        components = init_system(config)
        return components.supervisor, components.llm_client, components.tinvest

    def _get_trading_bars(self, all_candles: dict) -> list[int]:
        min_len = min(
            len(candles)
            for candles in all_candles.values()
            if candles
        ) if all_candles else 0

        if min_len == 0:
            return []

        all_indices = list(range(min_len))

        if self.config.interval == "1h":
            filtered = []
            for i in all_indices:
                first_candle = None
                for ticker in self.config.tickers:
                    candles = all_candles.get(ticker, [])
                    if i < len(candles):
                        first_candle = candles[i]
                        break

                if first_candle:
                    time_str = first_candle.get("time", "")
                    try:
                        if "T" in time_str:
                            hour = int(time_str.split("T")[1].split(":")[0])
                        else:
                            hour = 12

                        if self.config.trading_hours_start <= hour < self.config.trading_hours_end:
                            filtered.append(i)
                    except (ValueError, IndexError):
                        filtered.append(i)
            return filtered

        return all_indices
