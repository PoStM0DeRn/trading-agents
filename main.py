"""Trading Agents System — точка входа."""

import io
import logging
import sys
import argparse
from datetime import datetime, timezone

from tools.bootstrap import load_config, init_system, PROJECT_ROOT
from config.settings import validate_config
from config.secrets import secrets
from core.logging_setup import setup_logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

setup_logging()
logger = logging.getLogger("TradingSystem")


def main():
    parser = argparse.ArgumentParser(description="Trading Agents System")
    parser.add_argument("--stream", action="store_true", help="Start stream server for YouTube Live")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logger.info("Starting Trading Agents System...")
    config = load_config()
    errors = validate_config()
    if errors:
        for e in errors:
            logger.error(e)
        logger.error("Configuration validation failed. Exiting.")
        sys.exit(1)
    components = init_system(config, logger=logger)

    # Data cleanup
    from tools.memory import cleanup_old_data
    retention = config.get("trading", {}).get("retention_days", 90)
    cleanup_old_data(retention_days=retention)

    # Sentry
    if secrets.SENTRY_DSN:
        import sentry_sdk
        sentry_sdk.init(
            dsn=secrets.SENTRY_DSN,
            traces_sample_rate=0.2,
            profiles_sample_rate=0.1,
            environment="live" if not secrets.PAPER_TRADING else "paper",
        )
        logger.info("Sentry initialized")
        from tools.service import send_alert
        send_alert(f"System started in {'LIVE' if not secrets.PAPER_TRADING else 'PAPER'} mode", severity="info")

    # Live trading confirmation
    if not config.get("trading", {}).get("paper_trading", True):
        logger.critical("!!! LIVE TRADING MODE !!!")
        logger.critical("You are about to trade with REAL MONEY.")
        try:
            confirm = input("Type 'CONFIRM LIVE' to continue: ")
            if confirm != "CONFIRM LIVE":
                logger.info("Live trading cancelled by user")
                sys.exit(0)
        except (EOFError, KeyboardInterrupt):
            logger.info("Live trading cancelled by user")
            sys.exit(0)

    llm_client, client, supervisor = components.llm_client, components.tinvest, components.supervisor

    if args.stream:
        logger.info(f"Starting stream server on {args.host}:{args.port}")
        from stream.lmstudio_monitor import monitor as lm_monitor
        from stream.broadcaster import broadcaster
        from stream.agent_monitor import AgentMonitor
        from stream.server import init_server, run_server

        agent_monitor = AgentMonitor(str(PROJECT_ROOT / "data" / "trading_memory.db"))
        broadcaster.set_lmstudio_monitor(lm_monitor)
        broadcaster.set_agent_monitor(agent_monitor)
        broadcaster.set_config(config)
        llm_client.set_on_request(lm_monitor.record)
        init_server(
            broadcaster,
            health=supervisor.health,
            paper_trading=secrets.PAPER_TRADING,
            start_time=datetime.now(timezone.utc),
        )

        import threading
        def run_trading_loop():
            watchlist = config.get("watchlist", ["SBER"])
            cycle_interval = config.get("schedule", {}).get("cycle_interval_minutes", 15) * 60
            while True:
                try:
                    report = supervisor.run_trading_cycle(tickers=watchlist)
                    logger.info(f"Cycle complete: {report.get('orders_placed', 0)} orders placed")
                except Exception as e:
                    logger.error(f"Trading cycle error: {e}")
                import time
                time.sleep(cycle_interval)

        threading.Thread(target=run_trading_loop, daemon=True).start()
        run_server(host=args.host, port=args.port)
    else:
        watchlist = config.get("watchlist", ["SBER"])
        cycle_timeout = config.get("schedule", {}).get("cycle_timeout", 600)
        logger.info(f"Running trading cycle for: {watchlist} (timeout: {cycle_timeout}s)")
        try:
            report = supervisor.run_trading_cycle(tickers=watchlist, max_iterations=cycle_timeout // 100)
            logger.info("=== CYCLE REPORT ===")
            logger.info(f"  Tickers analyzed: {len(report['tickers_analyzed'])}")
            logger.info(f"  Proposals generated: {report['proposals_generated']}")
            logger.info(f"  Proposals approved: {report['proposals_approved']}")
            logger.info(f"  Orders placed: {report['orders_placed']}")
            if report['errors']:
                logger.warning(f"  Errors: {report['errors']}")
            return report
        except Exception as e:
            logger.error(f"Trading cycle failed: {e}", exc_info=True)
            raise
        finally:
            client.close()
            llm_client.close()


if __name__ == "__main__":
    main()
