"""Memory Agent — долговременная память системы."""

import json
import logging
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from tools import memory as memory_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)




class MemoryAgent(BaseAgent):
    """Агент памяти."""

    def __init__(self, llm_client, tools: dict = None):
        super().__init__(
            name="Memory",
            llm_client=llm_client,
            system_prompt=load_prompt("memory"),
            tools=self._build_tools({
                "store_trade": memory_tools.store_trade,
                "find_similar_trades": memory_tools.find_similar_trades,
                "get_trade_statistics": memory_tools.get_trade_statistics,
                "store_event": memory_tools.store_event,
                "store_trade_context": memory_tools.store_trade_context,
                "get_trade_context": memory_tools.get_trade_context,
                "analyze_loss_pattern": memory_tools.analyze_loss_pattern,
                "get_strategy_performance": memory_tools.get_strategy_performance,
                "store_lesson": memory_tools.store_lesson,
                "get_relevant_warnings": memory_tools.get_relevant_warnings,
                "get_critical_blocks": memory_tools.get_critical_blocks,
            }, tools),
        )

    def process(self, input_data: dict) -> dict:
        """Обработка: управление памятью.

        input_data: {
            "action": "store_trade|search_similar|get_statistics|store_event|
                       analyze_loss|store_context|get_warnings|get_performance|
                       get_critical_blocks",
            "data": {...}
        }
        """
        action = input_data.get("action", "")
        data = input_data.get("data", {})

        if action == "store_trade":
            return self._store_trade(data)
        elif action == "search_similar":
            return self._search_similar(data)
        elif action == "get_statistics":
            return self._get_statistics(data)
        elif action == "store_event":
            return self._store_event(data)
        elif action == "analyze_loss":
            return self._analyze_loss(data)
        elif action == "store_context":
            return self._store_context(data)
        elif action == "get_warnings":
            return self._get_warnings(data)
        elif action == "get_performance":
            return self._get_performance(data)
        elif action == "get_critical_blocks":
            return self._get_critical_blocks(data)
        else:
            return self._format_message("memory_error", {
                "message": f"Unknown action: {action}",
            })

    def _store_trade(self, data: dict) -> dict:
        """Сохранение сделки."""
        trade_record = {
            "trade_id": data.get("trade_id", ""),
            "ticker": data.get("ticker", ""),
            "action": data.get("action", ""),
            "quantity": data.get("quantity", 0),
            "entry_price": data.get("entry_price", 0),
            "exit_price": data.get("exit_price"),
            "stop_loss": data.get("stop_loss", 0),
            "take_profit": data.get("take_profit", 0),
            "pnl": data.get("pnl"),
            "commission": data.get("commission", 0),
            "strategy": data.get("strategy", ""),
            "signal_context": data.get("signal_context", {}),
            "rationale": data.get("rationale", ""),
            "opened_at": data.get("opened_at", datetime.now(timezone.utc).isoformat()),
            "closed_at": data.get("closed_at"),
            "status": data.get("status", "open"),
        }

        success = self._call_tool("store_trade", trade_record=trade_record)

        result = self._format_message("memory_store", {
            "trade_id": trade_record["trade_id"],
            "status": "stored" if success else "error",
            "message": "Trade saved" if success else "Failed to save trade",
        })

        self.log_action(
            input_data={"action": "store_trade", "trade_id": trade_record["trade_id"], "ticker": trade_record["ticker"]},
            output_data=result,
            tool_calls=["store_trade"],
        )

        return result

    def _search_similar(self, data: dict) -> dict:
        """Поиск похожих сделок через LLM-анализ критериев."""
        query = data.get("query", "")
        limit = data.get("limit", 5)

        criteria_prompt = f"""Extract trading search criteria from this query: "{query}"

Return JSON with these fields (use null for unknown):
- ticker: stock ticker or null
- action: LONG or SHORT or null
- strategy: strategy name or null
- min_confidence: minimum confidence (0-1) or null
- date_from: YYYY-MM-DD or null
- date_to: YYYY-MM-DD or null"""

        try:
            criteria = self._call_llm(criteria_prompt)
        except Exception:
            criteria = {}

        results = self._call_tool(
            "find_similar_trades",
            ticker=criteria.get("ticker"),
            action=criteria.get("action"),
            strategy=criteria.get("strategy"),
            limit=limit,
        )

        return self._format_message("memory_search_result", {
            "query": query,
            "criteria": criteria,
            "results": results,
            "count": len(results) if isinstance(results, list) else 0,
        })

    def _get_statistics(self, data: dict) -> dict:
        """Получение статистики."""
        strategy = data.get("strategy")
        period = data.get("period")

        stats = self._call_tool(
            "get_trade_statistics",
            strategy_name=strategy,
            period=period,
        )

        return self._format_message("memory_statistics", {
            "strategy": strategy,
            "period": period,
            "statistics": stats,
        })

    def _store_event(self, data: dict) -> dict:
        """Сохранение события."""
        event_record = {
            "event_type": data.get("event_type", ""),
            "ticker": data.get("ticker", ""),
            "description": data.get("description", ""),
            "impact_score": data.get("impact_score", 0),
            "sentiment": data.get("sentiment", "neutral"),
            "source": data.get("source", ""),
            "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }

        success = self._call_tool("store_event", event_record=event_record)

        result = self._format_message("memory_store", {
            "status": "stored" if success else "error",
            "message": "Event saved" if success else "Failed to save event",
        })

        self.log_action(
            input_data={"action": "store_event", "event_type": event_record["event_type"], "ticker": event_record["ticker"]},
            output_data=result,
            tool_calls=["store_event"],
        )

        return result

    def _store_context(self, data: dict) -> dict:
        """Сохранение контекста сделки (рыночные условия на момент открытия)."""
        trade_id = data.get("trade_id", "")
        ticker = data.get("ticker", "")
        market_snapshot = data.get("market_snapshot", {})
        news_briefing = data.get("news_briefing", {})

        success = self._call_tool(
            "store_trade_context",
            trade_id=trade_id,
            ticker=ticker,
            market_snapshot=market_snapshot,
            news_briefing=news_briefing,
        )

        result = self._format_message("memory_context", {
            "trade_id": trade_id,
            "status": "stored" if success else "error",
        })

        self.log_action(
            input_data={"action": "store_context", "trade_id": trade_id, "ticker": ticker},
            output_data=result,
            tool_calls=["store_trade_context"],
        )

        return result

    def _analyze_loss(self, data: dict) -> dict:
        """Анализ убыточной сделки: SQL-паттерны + LLM root cause.

        input_data: {
            "action": "analyze_loss",
            "data": {"trade_id": "..."}
        }
        """
        trade_id = data.get("trade_id", "")
        if not trade_id:
            return self._format_message("loss_analysis", {
                "trade_id": trade_id,
                "status": "error",
                "message": "No trade_id provided",
            })

        # 1. Загружаем сделку
        try:
            import sqlite3
            from tools.memory import get_db_path
            conn = sqlite3.connect(get_db_path(), timeout=5)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
            trade = cursor.fetchone()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to load trade {trade_id}: {e}")
            return self._format_message("loss_analysis", {
                "trade_id": trade_id,
                "status": "error",
                "message": str(e),
            })

        if not trade:
            return self._format_message("loss_analysis", {
                "trade_id": trade_id,
                "status": "error",
                "message": "Trade not found",
            })

        trade = dict(trade)
        pnl = trade.get("pnl")
        ticker = trade.get("ticker", "")
        strategy = trade.get("strategy", "")

        # 2. Если прибыльная — не анализируем
        if pnl is not None and pnl >= 0:
            return self._format_message("loss_analysis", {
                "trade_id": trade_id,
                "status": "skipped",
                "message": "Trade is profitable, no loss analysis needed",
            })

        # 3. Получаем контекст сделки
        context = self._call_tool("get_trade_context", trade_id=trade_id)
        conditions = memory_tools._extract_conditions(context)

        # 4. SQL- анализ паттернов
        patterns = self._call_tool(
            "analyze_loss_pattern",
            ticker=ticker,
            strategy=strategy,
            min_trades=3,
        )

        # 5. Статистика стратегии на тикере
        performance = self._call_tool(
            "get_strategy_performance",
            ticker=ticker,
            strategy=strategy,
        )

        # 6. Если есть паттерны с win_rate < 40% и >= 3 наблюдений — LLM анализ
        critical_patterns = [
            p for p in patterns
            if p.get("win_rate", 100) < 40 and p.get("times_observed", 0) >= 3
        ]

        if not critical_patterns:
            logger.info(f"No critical loss patterns found for {ticker}/{strategy}")
            return self._format_message("loss_analysis", {
                "trade_id": trade_id,
                "status": "no_pattern",
                "message": "No critical loss patterns detected yet",
                "patterns_found": len(patterns),
                "performance": performance,
            })

        # 7. LLM анализ root cause
        llm_prompt = f"""Analyze why this trade lost money and identify the root cause.

LOST TRADE:
- Ticker: {ticker}
- Strategy: {strategy}
- Action: {trade.get('action', '?')}
- Entry: {trade.get('entry_price', 0)}, Exit: {trade.get('exit_price', 0)}
- P&L: {trade.get('pnl', 0):.2f} RUB
- Rationale at entry: {trade.get('rationale', 'N/A')}

MARKET CONDITIONS AT ENTRY:
{json.dumps(context, ensure_ascii=False, indent=2)}

HISTORICAL LOSS PATTERNS (same ticker+strategy):
{json.dumps(critical_patterns, ensure_ascii=False, indent=2)}

STRATEGY PERFORMANCE:
{json.dumps(performance, ensure_ascii=False, indent=2)}

Analyze:
1. What specific market conditions caused this loss?
2. Why does this strategy fail in these conditions?
3. What is the recurring pattern?

Return JSON:
{
  "root_cause": "One-sentence root cause",
  "pattern_description": "Detailed pattern description",
  "conditions": {{
    "rsi_bucket": "...",
    "volatility_regime": "...",
    "sentiment_label": "...",
    "trend": "..."
  }},
  "confidence": 0.0-1.0,
  "severity": "info|warning|critical"
}"""

        try:
            llm_analysis = self._call_llm(llm_prompt)
        except Exception as e:
            logger.error(f"LLM loss analysis failed: {e}")
            llm_analysis = {
                "root_cause": f"LLM analysis failed: {e}",
                "pattern_description": f"Loss on {ticker} with {strategy}",
                "conditions": conditions,
                "confidence": 0.3,
                "severity": "info",
            }

        # 8. Сохраняем lesson
        severity = llm_analysis.get("severity", "warning")
        times_lost = max(
            critical_patterns[0].get("times_lost", 1) if critical_patterns else 1,
            1,
        )
        times_observed = max(
            critical_patterns[0].get("times_observed", 1) if critical_patterns else 1,
            1,
        )
        win_rate = critical_patterns[0].get("win_rate", 0) if critical_patterns else 0

        lesson = {
            "trade_id": trade_id,
            "ticker": ticker,
            "strategy": strategy,
            "lesson_type": "pattern",
            "pattern_description": llm_analysis.get(
                "pattern_description",
                llm_analysis.get("root_cause", f"Loss on {ticker}"),
            ),
            "conditions": llm_analysis.get("conditions", conditions),
            "confidence": llm_analysis.get("confidence", 0.5),
            "times_observed": times_observed,
            "times_lost": times_lost,
            "win_rate": win_rate,
            "severity": severity,
        }

        self._call_tool("store_lesson", lesson=lesson)

        logger.info(
            f"Loss lesson stored: {ticker}/{strategy} — "
            f"win_rate={win_rate}%, severity={severity}"
        )

        result = self._format_message("loss_analysis", {
            "trade_id": trade_id,
            "status": "lesson_stored",
            "root_cause": llm_analysis.get("root_cause"),
            "severity": severity,
            "win_rate": win_rate,
            "times_lost": times_lost,
            "lesson": lesson,
        })

        self.log_action(
            input_data={"action": "analyze_loss", "trade_id": trade_id, "ticker": ticker, "strategy": strategy},
            output_data=result,
            tool_calls=["store_lesson", "analyze_loss_pattern", "get_strategy_performance"],
        )

        return result

    def _get_warnings(self, data: dict) -> dict:
        """Получить релевантные предупреждения для текущих условий."""
        ticker = data.get("ticker", "")
        strategy = data.get("strategy")
        current_conditions = data.get("current_conditions", {})

        warnings = self._call_tool(
            "get_relevant_warnings",
            ticker=ticker,
            strategy=strategy,
            current_conditions=current_conditions,
        )

        result = self._format_message("warnings_result", {
            "ticker": ticker,
            "strategy": strategy,
            "warnings": warnings,
            "count": len(warnings) if isinstance(warnings, list) else 0,
        })

        self.log_action(
            input_data={"action": "get_warnings", "ticker": ticker, "strategy": strategy},
            output_data=result,
            tool_calls=["get_relevant_warnings"],
        )

        return result

    def _get_performance(self, data: dict) -> dict:
        """Получить статистику стратегии на тикере."""
        ticker = data.get("ticker", "")
        strategy = data.get("strategy", "")

        perf = self._call_tool(
            "get_strategy_performance",
            ticker=ticker,
            strategy=strategy,
        )

        return self._format_message("performance_result", {
            "ticker": ticker,
            "strategy": strategy,
            "performance": perf,
        })

    def _get_critical_blocks(self, data: dict) -> dict:
        """Получить критические блокировки."""
        ticker = data.get("ticker", "")
        strategy = data.get("strategy")

        blocks = self._call_tool(
            "get_critical_blocks",
            ticker=ticker,
            strategy=strategy,
        )

        return self._format_message("critical_blocks", {
            "ticker": ticker,
            "strategy": strategy,
            "blocks": blocks,
            "count": len(blocks) if isinstance(blocks, list) else 0,
            "blocked": len(blocks) > 0 if isinstance(blocks, list) else False,
        })
