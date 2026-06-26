"""Test scanner with sector mapping."""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

token = os.getenv('TINVEST_TOKEN', '')

from tools.ticker_scanner import set_clients, scan_market, TICKER_SECTORS
from integrations.tinvest import TInvestClient

# Create a mock LLM client
class MockLLM:
    def is_available(self):
        return False

# Initialize
tinvest_client = TInvestClient(token=token, account_id='')
tinvest_client.connect()

set_clients(MockLLM(), tinvest_client, {'tinvest': {'token': token}})

# Run scan without LLM
result = scan_market(max_picks=5, sectors=None, min_volume=0, use_llm=False)

logger.info(f"Method: {result.get('method')}")
logger.info(f"Total scanned: {result.get('total_scanned')}")
logger.info(f"Filtered: {result.get('filtered_count')}")
logger.info(f"Selected: {len(result.get('selected_tickers', []))}")

for t in result.get('selected_tickers', []):
    logger.info(f"  {t['ticker']}: {t['reason']}")

tinvest_client.close()
