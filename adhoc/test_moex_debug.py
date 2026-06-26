"""Debug MOEX scanner API response."""
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

from tinkoff.invest import Client
from tinkoff.invest.schemas import InstrumentStatus

logger.info("Connecting to T-Invest API...")

with Client(token=token) as client:
    instruments = client.instruments
    logger.info("Fetching shares...")
    
    response = instruments.shares(
        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
    )
    
    logger.info(f'Total instruments: {len(response.instruments)}')
    
    # Check first 10 instruments
    for i, inst in enumerate(response.instruments[:10]):
        logger.info(f'{i+1}. {inst.ticker} - class_code: {inst.class_code} - name: {inst.name}')
    
    # Count TQBR
    tqbr_count = sum(1 for inst in response.instruments if inst.class_code == 'TQBR')
    logger.info(f'\nTQBR instruments: {tqbr_count}')
    
    # Show some TQBR examples
    tqbr_examples = [inst for inst in response.instruments if inst.class_code == 'TQBR'][:5]
    logger.info('\nTQBR examples:')
    for inst in tqbr_examples:
        logger.info(f'  {inst.ticker}: {inst.name}')
