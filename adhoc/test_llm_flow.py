import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from tools.bootstrap import load_config, init_system

config = load_config()
components = init_system(config)
llm_client, client, supervisor = components.llm_client, components.tinvest, components.supervisor

report = supervisor.run_trading_cycle(tickers=["SBER"], max_iterations=1)

logger.info("=== RESULT ===")
logger.info("Tickers: %s", report["tickers_analyzed"])
logger.info("Proposals: %s", report["proposals_generated"])
logger.info("Approved: %s", report["proposals_approved"])
logger.info("Executed: %s", report["orders_placed"])
logger.info("Errors: %s", report["errors"])

for step in report.get("steps", []):
    for p in step.get("proposals", []):
        logger.info("  Proposal: %s conf=%s strategy=%s", p.get('action'), f"{p.get('confidence',0):.0%}", p.get('strategy'))
        logger.info("  Rationale: %s", p.get('rationale','')[:200])

client.close()
llm_client.close()
