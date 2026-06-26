"""Critic Agent — проверка торговых идей на логику и риски."""

import json
import logging
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from tools import memory as memory_tools
from tools import short_specific as short_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)




class CriticAgent(BaseAgent):
    """Агент-критик."""

    def __init__(self, llm_client, tools: dict = None):
        super().__init__(
            name="Critic",
            llm_client=llm_client,
            system_prompt=load_prompt("critic"),
            tools=self._build_tools({
                "find_similar_trades": memory_tools.find_similar_trades,
                "get_trade_statistics": memory_tools.get_trade_statistics,
                "get_short_interest": short_tools.get_short_interest,
                "get_borrow_rate": short_tools.get_borrow_rate,
                "check_short_availability": short_tools.check_short_availability,
                "get_dividend_calendar": short_tools.get_dividend_calendar,
            }, tools),
        )

    def process(self, input_data: dict) -> dict:
        """Обработка: проверка торгового предложения.

        input_data: {
            "proposal": {...},
            "news_briefing": {...},
            "market_snapshot": {...}
        }
        """
        proposal = input_data.get("proposal", {})
        proposal_id = proposal.get("id", "")
        action = proposal.get("action", "HOLD")
        ticker = proposal.get("ticker", "")

        # Собираем дополнительные данные для проверки
        context = {}

        # Проверка истории
        try:
            stats = self._call_tool("get_trade_statistics")
            context["trade_stats"] = stats
        except Exception as e:
            logger.warning(f"Failed to get trade stats: {e}")

        # Стратегия и тикер для поиска паттернов
        strategy = proposal.get("strategy", "")
        ticker = proposal.get("ticker", "")

        # ── Learning: историческая производительность стратегии ──
        strategy_performance = {}
        try:
            strategy_performance = memory_tools.get_strategy_performance(
                ticker=ticker, strategy=strategy
            )
            if strategy_performance.get("total_trades", 0) > 0:
                context["strategy_performance"] = strategy_performance
        except Exception as e:
            logger.warning(f"Failed to get strategy performance: {e}")

        # ── Learning: релевантные предупреждения ──
        relevant_warnings = []
        try:
            relevant_warnings = memory_tools.get_relevant_warnings(
                ticker=ticker,
                strategy=strategy,
                limit=5,
            )
            if relevant_warnings:
                context["relevant_warnings"] = relevant_warnings
        except Exception as e:
            logger.warning(f"Failed to get relevant warnings: {e}")

        # ── Learning: критические блокировки ──
        critical_blocks = []
        try:
            critical_blocks = memory_tools.get_critical_blocks(
                ticker=ticker,
                strategy=strategy,
            )
            if critical_blocks:
                context["critical_blocks"] = critical_blocks
        except Exception as e:
            logger.warning(f"Failed to get critical blocks: {e}")

        # Для шортов — специфические проверки
        if "SHORT" in action:
            try:
                short_interest = self._call_tool("get_short_interest", ticker=ticker)
                borrow_rate = self._call_tool("get_borrow_rate", ticker=ticker)
                short_avail = self._call_tool("check_short_availability", ticker=ticker)
                dividends = self._call_tool(
                    "get_dividend_calendar",
                    ticker=ticker,
                    date_from=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                )
                context["short_data"] = {
                    "short_interest": short_interest,
                    "borrow_rate": borrow_rate,
                    "availability": short_avail,
                    "dividends": dividends,
                }
            except Exception as e:
                logger.warning(f"Failed to get short data: {e}")

        # LLM выносит вердикт
        historical_section = ""

        perf = context.get("strategy_performance", {})
        if perf.get("total_trades", 0) > 0:
            historical_section += f"""
HISTORICAL PERFORMANCE of {strategy} on {ticker}:
- Total trades: {perf.get('total_trades', 0)}
- Win rate: {perf.get('win_rate', 0)}%
- Wins: {perf.get('wins', 0)}, Losses: {perf.get('losses', 0)}
- Average P&L: {perf.get('avg_pnl', 0):.2f} RUB
- Total P&L: {perf.get('total_pnl', 0):.2f} RUB
"""

        warnings = context.get("relevant_warnings", [])
        if warnings:
            historical_section += "\nRELEVANT LOSS PATTERNS:\n"
            for w in warnings:
                sev = w.get("severity", "info").upper()
                desc = w.get("pattern_description", "Unknown")
                wr = w.get("win_rate", 0)
                historical_section += f"- [{sev}] {desc} (win rate: {wr}%)\n"

        blocks = context.get("critical_blocks", [])
        if blocks:
            historical_section += "\n!!! CRITICAL BLOCKS ACTIVE !!!\n"
            for b in blocks:
                historical_section += f"- BLOCKED: {b.get('pattern_description', 'Unknown')}\n"
            historical_section += "You MUST reject this proposal if it matches a blocked pattern.\n"

        prompt = f"""Review this trade proposal:

PROPOSAL:
{json.dumps(proposal, ensure_ascii=False, indent=2)}

ADDITIONAL CONTEXT:
{json.dumps(context, ensure_ascii=False, indent=2)}
{historical_section}
Evaluate:
1. Is the rationale logically consistent with the data?
2. Is the stop loss level reasonable?
3. Are the risks acceptable?
4. For shorts: check short squeeze risk, borrow cost, dividend dates
5. Will commissions significantly impact profitability?
6. Does this trade match a known losing pattern? If yes, REJECT.

Return your verdict as JSON. Example:
{{"status": "Approved", "adjusted_confidence": 0.8, "warnings": [], "rationale": "Good setup with clear support"}}"""

        try:
            verdict = self._call_llm(prompt, context=context)
        except Exception as e:
            logger.error(f"Critic LLM failed: {e}")
            verdict = {
                "status": "Rejected",
                "adjusted_confidence": 0,
                "warnings": [f"LLM analysis failed: {e}"],
            }

        result = self._format_message("critic_verdict", {
            "proposal_id": proposal_id,
            "status": verdict.get("status", "Rejected"),
            "adjusted_confidence": min(max(float(verdict.get("adjusted_confidence", 0)), 0), 1),
            "warnings": verdict.get("warnings", []),
            "recommendations": verdict.get("recommendations", {}),
            "rationale": verdict.get("rationale", ""),
        })

        self.log_action(
            input_data={"proposal_id": proposal_id, "ticker": ticker},
            output_data=result,
            tool_calls=["get_trade_statistics", "llm_review"],
        )

        return result
