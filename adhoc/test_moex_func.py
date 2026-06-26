"""Debug get_all_moex_shares function."""
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
logger.info("Token loaded")

from integrations.moex_scanner import get_all_moex_shares, _listing_cache, _cache_timestamp
import integrations.moex_scanner as scanner

logger.info(f'Initial cache: {len(_listing_cache)} shares')
logger.info(f'Cache timestamp: {_cache_timestamp}')

# Call the function
shares = get_all_moex_shares(token=token, only_tradable=True)
logger.info(f'Shares found: {len(shares)}')

# Check the cache after call
logger.info(f'After call cache: {len(scanner._listing_cache)} shares')
logger.info(f'After call timestamp: {scanner._cache_timestamp}')
