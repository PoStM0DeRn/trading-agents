import argparse
import logging
import sys

from .config import BacktestConfig
from .engine import BacktestEngine

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        prog="python -m backtester",
        description="Backtest trading strategies on MOEX historical data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backtester --tickers SBER,GAZP --period 3m --interval 1h
  python -m backtester --tickers SBER --period 1y --interval 1d --capital 200000
  python -m backtester --tickers SBER,LKOH,YDEX --period 6m --interval 1h --verbose
        """,
    )

    parser.add_argument(
        "--tickers",
        type=str,
        default="SBER,GAZP,LKOH,GMKN,YDEX,VTBR,ROSN,NVTK",
        help="Comma-separated list of MOEX tickers (default: all 8)",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="1y",
        choices=["3m", "6m", "1y", "2y"],
        help="Backtest period (default: 1y)",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1h",
        choices=["1h", "4h", "1d"],
        help="Candle interval (default: 1h)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100000.0,
        help="Initial capital in RUB (default: 100000)",
    )
    parser.add_argument(
        "--leverage",
        type=float,
        default=3.0,
        help="Maximum leverage (default: 3.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="backtest_results",
        help="Output directory for reports (default: backtest_results/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    tickers = [t.strip().upper() for t in args.tickers.split(",")]

    config = BacktestConfig(
        tickers=tickers,
        period=args.period,
        interval=args.interval,
        initial_capital=args.capital,
        max_leverage=args.leverage,
        output_dir=args.output,
        verbose=args.verbose,
    )

    engine = BacktestEngine(config)
    results = engine.run()

    if "error" in results:
        logger.error(f"\nBacktest failed: {results['error']}")
        sys.exit(1)

    logger.info(f"\nResults saved to: {config.output_dir}/")


if __name__ == "__main__":
    main()
