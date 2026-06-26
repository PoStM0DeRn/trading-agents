"""Quick test for paper trading mode."""

from agents.supervisor import SupervisorAgent
from integrations.lmstudio_client import LMStudioClient
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

config = {
    "paper_trading": True,
    "initial_capital": 100000,
    "watchlist": ["SBER"],
}

client = LMStudioClient()
supervisor = SupervisorAgent(client, config=config)

logger.info("=== Testing paper trading ===")
report = supervisor.run_trading_cycle(tickers=["SBER"])
logger.info("Capital:", report.get("capital"))
logger.info("Proposals:", report.get("proposals_generated"))
logger.info("Approved:", report.get("proposals_approved"))
logger.info("Executed:", report.get("orders_placed"))
