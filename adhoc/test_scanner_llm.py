"""Test scanner with LLM."""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from tools.bootstrap import load_config, init_system
from tools.ticker_scanner import set_clients, scan_market

config = load_config()
components = init_system(config)
llm_client, client, supervisor = components.llm_client, components.tinvest, components.supervisor

# Initialize scanner
set_clients(llm_client, client, config)

# Run scan with LLM
result = scan_market(max_picks=5, sectors=None, min_volume=0, use_llm=True)

logger.info(f"Method: {result.get('method')}")
logger.info(f"Total scanned: {result.get('total_scanned')}")
logger.info(f"Selected: {len(result.get('selected_tickers', []))}")

for t in result.get('selected_tickers', []):
    logger.info(f"  {t['ticker']}: {t['reason']} (score: {t.get('score', '?')})")

client.close()
llm_client.close()
