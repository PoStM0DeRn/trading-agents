import logging
import sqlite3
from datetime import datetime, timezone
import sys
sys.path.insert(0, '.')
from tools.memory import get_db_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conn = sqlite3.connect(get_db_path())
cursor = conn.cursor()

# Clear positions
cursor.execute('DELETE FROM virtual_positions')
logger.info('Positions cleared: %s', cursor.rowcount)

# Reset account
now = datetime.now(timezone.utc).isoformat()
cursor.execute('UPDATE virtual_account SET initial_capital=100000, current_balance=100000, borrowed=0, updated_at=? WHERE id=1', (now,))
logger.info('Account reset to 100,000 RUB')

# Clear trades
cursor.execute('DELETE FROM trades')
logger.info('Trades cleared: %s', cursor.rowcount)

conn.commit()

# Verify
cursor.execute('SELECT initial_capital, current_balance FROM virtual_account WHERE id=1')
row = cursor.fetchone()
logger.info('Verified balance: %,.2f RUB', row[1])

cursor.execute('SELECT COUNT(*) FROM virtual_positions')
logger.info('Open positions: %s', cursor.fetchone()[0])

conn.close()
