"""Test Russian news sources."""

from tools.news import search_news, _get_company_name

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

logger.info("=== Testing Russian News Sources ===")

for ticker in ["SBER", "GAZP", "LKOH", "ROSN"]:
    company = _get_company_name(ticker)
    logger.info(f"\n{ticker} -> {company}")
    articles = search_news(ticker, limit=3)
    logger.info(f"  Found: {len(articles)} articles")
    for a in articles[:2]:
        headline = a["headline"][:60]
        source = a["source"]
        logger.info(f"  - [{source}] {headline}...")
