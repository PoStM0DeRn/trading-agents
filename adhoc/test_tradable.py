"""Debug tradable filter."""
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

from tinkoff.invest import Client
from tinkoff.invest.schemas import InstrumentStatus

with Client(token=token) as client:
    instruments = client.instruments
    response = instruments.shares(
        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
    )
    
    # Check TQBR instruments
    tqbr = [inst for inst in response.instruments if inst.class_code == 'TQBR']
    logger.info(f'Total TQBR: {len(tqbr)}')
    
    # Check d_long and d_short attributes
    for inst in tqbr[:5]:
        d_long = getattr(inst, 'd_long', 'MISSING')
        d_short = getattr(inst, 'd_short', 'MISSING')
        logger.info(f'{inst.ticker}: d_long={d_long}, d_short={d_short}')
    
    # Count tradable
    tradable = [inst for inst in tqbr if getattr(inst, 'd_long', False) and getattr(inst, 'd_short', False)]
    logger.info(f'\nTradable TQBR: {len(tradable)}')
