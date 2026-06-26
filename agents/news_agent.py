"""News Intelligence Agent — мониторинг новостей и анализ тональности."""

import json
import logging
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from tools import news as news_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)




class NewsIntelligenceAgent(BaseAgent):
    """Агент новостного анализа."""

    def __init__(self, llm_client, tools: dict = None):
        super().__init__(
            name="NewsIntelligence",
            llm_client=llm_client,
            system_prompt=load_prompt("news"),
            tools=self._build_tools({
                "search_news": news_tools.search_news,
                "fetch_article": news_tools.fetch_article,
                "get_news_sentiment": news_tools.get_news_sentiment,
                "detect_entities": news_tools.detect_entities,
                "classify_impact": news_tools.classify_impact,
            }, tools),
        )

    def process(self, input_data: dict) -> dict:
        """Обработка: сбор новостей и формирование брифинга.

        input_data: {"ticker": "AAPL", "period": "7d"}
        """
        ticker = input_data.get("ticker", "")

        # Шаг 1: Поиск новостей
        articles = self._call_tool("search_news", ticker=ticker, limit=15)

        if not articles:
            return self._format_message("news_briefing", {
                "ticker": ticker,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "events": [],
                "overall_sentiment": "neutral",
                "overall_impact": 0.0,
            })

        # Шаг 2: Анализ тональности
        sentiment = self._call_tool("get_news_sentiment", ticker=ticker)

        # Шаг 3: LLM анализирует каждую новость
        analysis_prompt = f"""Analyze these news articles about {ticker}:

{json.dumps(articles[:10], ensure_ascii=False, indent=2)}

Overall sentiment data: {json.dumps(sentiment, ensure_ascii=False)}

For each article, determine:
- sentiment (positive/negative/neutral)
- impact_score (0-1): how much could this move the stock?
- relevance (direct/indirect/none): is this directly about {ticker}?
- summary (1 sentence)

Return JSON with "events" array and "overall_impact" (0-1)."""

        try:
            analysis = self._call_llm(analysis_prompt)
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}, using fallback")
            analysis = {"events": [], "overall_impact": 0.3}

        # Формируем брифинг
        briefing = self._format_message("news_briefing", {
            "ticker": ticker,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "events": analysis.get("events", [])[:5],
            "overall_sentiment": sentiment.get("positive", 0) > sentiment.get("negative", 0)
                and "positive" or "negative" if sentiment.get("positive", 0) != sentiment.get("negative", 0)
                else "neutral",
            "overall_impact": analysis.get("overall_impact", 0.3),
        })

        self.log_action(
            input_data=input_data,
            output_data=briefing,
            tool_calls=["search_news", "get_news_sentiment", "llm_analyze"],
        )

        return briefing
