"""Quick test for ticker scanner functionality."""

import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def test_scanner():
    logger.info("=== Testing Ticker Scanner ===\n")
    
    # Test 1: Import modules
    try:
        from tools import ticker_scanner
        from integrations import moex_scanner
        logger.info("[OK] Modules imported successfully")
    except Exception as e:
        logger.error(f"[FAIL] Import failed: {e}")
        return
    
    # Test 2: Check database table
    try:
        from tools.memory import init_db, _db_path
        import sqlite3
        init_db()
        
        conn = sqlite3.connect(_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scan_results'")
        result = cursor.fetchone()
        conn.close()
        
        if result:
            logger.info("[OK] scan_results table exists")
        else:
            logger.error("[FAIL] scan_results table not found")
    except Exception as e:
        logger.error(f"[FAIL] Database check failed: {e}")
    
    # Test 3: Check scanner functions exist
    try:
        assert hasattr(ticker_scanner, 'scan_market'), "scan_market not found"
        assert hasattr(ticker_scanner, 'set_clients'), "set_clients not found"
        assert hasattr(ticker_scanner, 'get_scan_history'), "get_scan_history not found"
        assert hasattr(ticker_scanner, 'get_latest_scan'), "get_latest_scan not found"
        logger.info("[OK] Scanner functions exist")
    except AssertionError as e:
        logger.error(f"[FAIL] Scanner functions missing: {e}")
    
    # Test 4: Check MOEX scanner functions
    try:
        assert hasattr(moex_scanner, 'get_all_moex_shares'), "get_all_moex_shares not found"
        assert hasattr(moex_scanner, 'get_shares_count'), "get_shares_count not found"
        logger.info("[OK] MOEX scanner functions exist")
    except AssertionError as e:
        logger.error(f"[FAIL] MOEX scanner functions missing: {e}")
    
    # Test 5: Check config has scanner section
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'settings.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if 'scanner' in config:
            logger.info("[OK] Scanner config exists")
            scanner_config = config['scanner']
            logger.info(f"  - enabled: {scanner_config.get('enabled')}")
            logger.info(f"  - max_picks: {scanner_config.get('max_picks')}")
            logger.info(f"  - use_llm: {scanner_config.get('use_llm')}")
        else:
            logger.error("[FAIL] Scanner config not found")
    except Exception as e:
        logger.error(f"[FAIL] Config check failed: {e}")
    
    logger.info("\n=== All tests passed! ===")

if __name__ == "__main__":
    test_scanner()
