"""Test MOEX scanner with actual token."""
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

from integrations.moex_scanner import get_all_moex_shares

shares = get_all_moex_shares(token=token, only_tradable=True)
logger.info(f'Found {len(shares)} shares')

if shares:
    tickers = [s['ticker'] for s in shares[:10]]
    logger.info(f'First 10: {tickers}')
    logger.info(f'Sample share: {shares[0]}')
