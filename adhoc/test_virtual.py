from tools.memory import init_db
from tools import virtual_portfolio
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

init_db("data/trading_memory.db")
logger.info("DB initialized")

# Test open position
result = virtual_portfolio.open_position(
    ticker="SBER",
    side="LONG",
    quantity=100,
    entry_price=319.50,
    stop_loss=317.0,
    take_profit=327.0,
    commission=30.68,
    strategy="contrarian",
    rationale="RSI oversold near support",
)
logger.info("Open:", result)

# Check balance
bal = virtual_portfolio.get_balance()
logger.info("Balance:", bal)

# Check positions
positions = virtual_portfolio.get_positions()
logger.info("Positions:", len(positions))
for p in positions:
    logger.info("  " + p["ticker"] + " " + p["side"] + " " + str(p["quantity"]) + " @ " + str(p["entry_price"]))

# Test close
if positions:
    close_result = virtual_portfolio.close_position(positions[0]["trade_id"], close_price=325.0)
    logger.info("Close:", close_result)

# Final balance
bal2 = virtual_portfolio.get_balance()
logger.info("Final balance:", bal2)
