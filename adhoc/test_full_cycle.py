import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from tools.bootstrap import load_config, init_system

config = load_config()
components = init_system(config)
llm_client, client, supervisor = components.llm_client, components.tinvest, components.supervisor

# Reset account
from tools import virtual_portfolio
virtual_portfolio.reset_account(100000)
logger.info("Account reset to 100000 RUB")

report = supervisor.run_trading_cycle(tickers=["SBER"], max_iterations=1)

logger.info("=== RESULT ===")
logger.info("Tickers: %s", report["tickers_analyzed"])
logger.info("Proposals: %s", report["proposals_generated"])
logger.info("Approved: %s", report["proposals_approved"])
logger.info("Executed: %s", report["orders_placed"])

# Show positions
positions = virtual_portfolio.get_positions()
logger.info("Virtual positions: %s", len(positions))
for p in positions:
    logger.info("  %s %s %s @ %s", p["ticker"], p["side"], p["quantity"], p["entry_price"])

# Show balance
bal = virtual_portfolio.get_balance()
logger.info("Balance: %s", bal)

client.close()
llm_client.close()
