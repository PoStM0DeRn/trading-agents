"""Run a single trading cycle to verify all fixes work end-to-end."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from tools.bootstrap import load_config, init_system, PROJECT_ROOT
from config.settings import validate_config


def run_single_cycle():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    logger = logging.getLogger("TestCycle")

    logger.info("Loading configuration...")
    config = load_config()
    errors = validate_config()
    if errors:
        for e in errors:
            logger.error(e)
        logger.error("Configuration validation failed. Exiting.")
        return None
    components = init_system(config, logger=logger)
    llm_client, client, supervisor = components.llm_client, components.tinvest, components.supervisor

    if not llm_client.is_available():
        logger.error("LM Studio is not available!")
        return None

    logger.info("Running single trading cycle for SBER...")
    try:
        report = supervisor.run_trading_cycle(tickers=["SBER"], max_iterations=1)
        logger.info("=== CYCLE REPORT ===")
        logger.info(f"  Tickers analyzed: {report['tickers_analyzed']}")
        logger.info(f"  Proposals generated: {report['proposals_generated']}")
        logger.info(f"  Proposals approved: {report['proposals_approved']}")
        logger.info(f"  Orders placed: {report['orders_placed']}")
        if report['errors']:
            logger.warning(f"  Errors: {report['errors']}")
        for step in report.get('steps', []):
            ticker = step.get('ticker')
            proposals = step.get('proposals', [])
            logger.info(f"\n--- {ticker} ---")
            for p in proposals:
                logger.info(f"  Proposal: {p.get('action')} (confidence={p.get('confidence', 0):.0%}, strategy={p.get('strategy', '?')})")
        return report
    except Exception as e:
        logger.error(f"Cycle failed: {e}", exc_info=True)
        return None
    finally:
        client.close()
        llm_client.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    logger = logging.getLogger("RunCycle")
    report = run_single_cycle()
    if report:
        orders = report.get('orders_placed', 0)
        approved = report.get('proposals_approved', 0)
        logger.info("=" * 50)
        if orders > 0:
            logger.info(f"SUCCESS: {orders} order(s) placed!")
        elif approved > 0:
            logger.info(f"PARTIAL: {approved} proposal(s) approved but not executed")
        else:
            logger.info("NO TRADES: Check logs for rejection reasons")
        logger.info("=" * 50)
