import logging
import sqlite3
import sys
sys.path.insert(0, '.')
from tools.memory import get_db_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conn = sqlite3.connect(get_db_path())
cursor = conn.cursor()
cursor.execute("SELECT trade_id, ticker, side, quantity, entry_price, status FROM virtual_positions WHERE status='open'")
logger.info('Open positions: %s', cursor.fetchall())
cursor.execute("SELECT COUNT(*) FROM virtual_positions WHERE status='closed'")
logger.info('Closed positions: %s', cursor.fetchone()[0])
cursor.execute("SELECT * FROM virtual_account")
logger.info('Account: %s', cursor.fetchall())
conn.close()
