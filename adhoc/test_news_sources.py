"""Тестовый скрипт: сбор новостей из всех источников."""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)

from tools import news

TICKERS = {
    "SBER": "Сбербанк",
    "GAZP": "Газпром",
    "LKOH": "Лукойл",
}

SOURCES_ORDER = [
    "Google News RU",
    "TASS",
    "Interfax",
    "RBC",
    "Bing News RU",
    "Коммерсантъ",
    "Ведомости",
    "РИА Новости",
]


def test_all_sources():
    logger.info("=" * 70)
    logger.info("  ТЕСТ СИСТЕМЫ СБОРА НОВОСТЕЙ (9 источников)")
    logger.info("=" * 70)

    stats = {src: 0 for src in SOURCES_ORDER}
    stats["ИТОГО"] = 0

    for ticker, company in TICKERS.items():
        logger.info(f"\n{'=' * 70}")
        logger.info(f"  ТИКЕР: {ticker} ({company})")
        logger.info(f"{'=' * 70}")

        try:
            articles = news.search_news(ticker, limit=20)
        except Exception as e:
            logger.info(f"  ОШИБКА: {e}")
            articles = []

        by_source = {}
        for art in articles:
            src = art.get("source", "?")
            by_source.setdefault(src, []).append(art)
            stats["ИТОГО"] += 1

        for src in SOURCES_ORDER:
            src_articles = by_source.get(src, [])
            stats[src] += len(src_articles)
            status = f"{len(src_articles)} статей" if src_articles else "—"
            logger.info(f"\n  [{src}] {status}")
            for i, art in enumerate(src_articles[:3], 1):
                headline = art.get("headline", "")[:70].replace("\n", " ")
                logger.info(f"    {i}. {headline}")

    logger.info(f"\n{'=' * 70}")
    logger.info("  ИТОГО ПО ИСТОЧНИКАМ:")
    logger.info(f"{'=' * 70}")
    for src in SOURCES_ORDER:
        logger.info(f"  {src:20s} {stats[src]:3d}")
    logger.info(f"  {'—' * 30}")
    logger.info(f"  {'ИТОГО':20s} {stats['ИТОГО']:3d}")
    logger.info(f"{'=' * 70}")


if __name__ == "__main__":
    test_all_sources()
