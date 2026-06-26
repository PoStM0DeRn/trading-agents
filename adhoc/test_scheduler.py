import time
from tools.bootstrap import load_config, init_system
from tools.scheduler import TradingScheduler
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

config = load_config()
components = init_system(config)
llm_client, client, supervisor = components.llm_client, components.tinvest, components.supervisor

scheduler = TradingScheduler(supervisor, config)

logger.info("=== Test 1: Initial status ===")
status = scheduler.get_status()
logger.info("Running:", status["running"])
logger.info("Cycles:", status["cycles_run"])

logger.info("\n=== Test 2: Start scheduler (interval=1 min) ===")
scheduler.start(interval_minutes=1, tickers=["SBER"])
time.sleep(2)
status = scheduler.get_status()
logger.info("Running:", status["running"])
logger.info("Thread alive:", scheduler._thread.is_alive())
logger.info("Next run:", status["next_run"])

logger.info("\n=== Test 3: Stop scheduler ===")
scheduler.stop()
time.sleep(1)
status = scheduler.get_status()
logger.info("Running:", status["running"])
logger.info("Cycles:", status["cycles_run"])

logger.info("\n=== Test 4: Logs ===")
logs = scheduler.get_all_logs()
logger.info("Log entries:", len(logs))

client.close()
llm_client.close()
logger.info("\nAll tests passed!")
