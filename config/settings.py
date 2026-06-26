"""Configuration validation on startup."""

import logging

from config.secrets import secrets

logger = logging.getLogger(__name__)

REQUIRED_VARS = ["TINVEST_TOKEN", "TINVEST_ACCOUNT_ID"]
OPTIONAL_VARS = ["LMSTUDIO_HOST", "NEWS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]


def validate_config() -> list[str]:
    """Validate required environment variables are set.

    Returns a list of error messages. Empty list means all checks passed.
    """
    errors: list[str] = []
    for var in REQUIRED_VARS:
        if not getattr(secrets, var):
            errors.append(f"Missing required env var: {var}")
    for var in OPTIONAL_VARS:
        if not getattr(secrets, var):
            logger.info(f"Optional env var not set: {var} (will be skipped)")
    paper_trading = secrets.PAPER_TRADING
    if paper_trading and secrets.TINVEST_TOKEN:
        logger.info("[PAPER] Paper trading mode: no real orders will be placed")
    if not paper_trading:
        logger.warning("[LIVE] REAL MONEY TRADING MODE")
        if not secrets.TINVEST_TOKEN:
            errors.append("Live trading mode requires TINVEST_TOKEN")
    return errors
