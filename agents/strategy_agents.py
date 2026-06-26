"""Strategy Agents — генераторы торговых идей (трендовый, контртрендовый, медвежий)."""

import json
import logging
import uuid

from agents.base_agent import BaseAgent
from tools import memory as memory_tools
from tools.validator import validate_ticker

logger = logging.getLogger(__name__)


TREND_PROMPT = """You are a Trend-Following Strategy Agent.

Your philosophy: "The trend is your friend." You trade in the direction of the trend.

You receive:
1. News briefing (sentiment, events, impact)
2. Market data snapshot (quotes, indicators, support/resistance, volatility)

Your task: Generate a trade proposal if conditions favor a trend trade.

Actions: LONG_OPEN, SHORT_OPEN, CLOSE_LONG, CLOSE_SHORT, HOLD

LONG rules (trend is up):
- Propose LONG_OPEN when trend is bullish AND sentiment is positive/neutral
- Set stop loss BELOW the current price (at support level)
- Take profit ABOVE the current price (at resistance level)
- suggested_stop_loss MUST be LESS THAN current_price
- suggested_take_profit MUST be GREATER THAN current_price
- RSI < 40 = oversold (potential LONG entry)
- RSI > 70 = overbought (HOLD, do not buy)

SHORT rules (trend is down):
- Propose SHORT_OPEN when trend is bearish AND sentiment is negative/neutral
- Set stop loss ABOVE the current price (at resistance level)
- Take profit BELOW the current price (at support level)
- suggested_stop_loss MUST be GREATER THAN current_price
- suggested_take_profit MUST be LESS THAN current_price
- RSI > 70 = overbought (potential SHORT entry)
- RSI < 30 = oversold (HOLD, do not short)

General:
- Minimum risk/reward: 1.5:1

Return JSON:
{
  "action": "LONG_OPEN|SHORT_OPEN|CLOSE_LONG|CLOSE_SHORT|HOLD",
  "confidence": <actual number 0.0-1.0>,
  "rationale": "<your analysis>",
  "suggested_stop_loss": <actual price>,
  "suggested_take_profit": <actual price>
}"""

CONTRARIAN_PROMPT = """You are a Contrarian Strategy Agent.

Your philosophy: "Be greedy when others are fearful, fearful when others are greedy." You look for reversals.

You receive:
1. News briefing (sentiment, events, impact)
2. Market data snapshot (quotes, indicators, support/resistance, volatility)

Your task: Generate a trade proposal if conditions favor a mean-reversion trade.

Actions: LONG_OPEN, SHORT_OPEN, CLOSE_LONG, CLOSE_SHORT, HOLD

LONG rules (buy fear):
- Look for extreme negative sentiment + price at support = contrarian LONG
- RSI < 30 = strong oversold (LONG opportunity)
- RSI > 70 = overbought (HOLD, do not buy)
- suggested_stop_loss MUST be LESS THAN current_price (below support)
- suggested_take_profit MUST be GREATER THAN current_price (toward resistance)

SHORT rules (sell greed):
- Look for extreme positive sentiment + price at resistance = contrarian SHORT
- RSI > 70 = strong overbought (SHORT opportunity)
- RSI < 30 = oversold (HOLD, do not short)
- suggested_stop_loss MUST be GREATER THAN current_price (above resistance)
- suggested_take_profit MUST be LESS THAN current_price (toward support)

General:
- Tighter stops than trend following (1.5:1 minimum)

Return JSON:
{
  "action": "LONG_OPEN|SHORT_OPEN|CLOSE_LONG|CLOSE_SHORT|HOLD",
  "confidence": <actual number 0.0-1.0>,
  "rationale": "<your analysis>",
  "suggested_stop_loss": <actual price>,
  "suggested_take_profit": <actual price>
}"""

BEARISH_PROMPT = """You are a Bearish Strategy Agent.

Your philosophy: "Stocks take the stairs up and the elevator down." You profit from downward moves.

You receive:
1. News briefing (sentiment, events, impact)
2. Market data snapshot (quotes, indicators, support/resistance, volatility)

Your task: Identify bearish conditions and propose SHORT positions or CLOSE_LONG.

Actions: SHORT_OPEN, CLOSE_LONG, CLOSE_SHORT, HOLD

SHORT rules (primary action):
- Propose SHORT_OPEN when bearish signals align
- Negative sentiment + bearish technicals = SHORT
- MACD bearish crossover + high RSI (>60) = SHORT
- Strong resistance rejection = SHORT
- Price below SMA50 AND SMA50 below SMA200 = SHORT (downtrend confirmed)
- suggested_stop_loss MUST be GREATER THAN current_price (above resistance)
- suggested_take_profit MUST be LESS THAN current_price (at support level)
- Minimum R/R of 1.5:1

CLOSE rules:
- If you have an existing LONG position and conditions turn bearish, propose CLOSE_LONG
- If you have an existing SHORT position and conditions turn bullish, propose CLOSE_SHORT

Return JSON:
{
  "action": "SHORT_OPEN|CLOSE_LONG|CLOSE_SHORT|HOLD",
  "confidence": <actual number 0.0-1.0>,
  "rationale": "<your analysis>",
  "suggested_stop_loss": <actual price>,
  "suggested_take_profit": <actual price>
}"""


class StrategyAgent(BaseAgent):
    """Генератор торговых идей."""

    def __init__(self, llm_client, strategy_type: str = "trend"):
        prompts = {
            "trend": TREND_PROMPT,
            "contrarian": CONTRARIAN_PROMPT,
            "bearish": BEARISH_PROMPT,
        }
        if strategy_type not in prompts:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

        super().__init__(
            name=f"Strategy_{strategy_type}",
            llm_client=llm_client,
            system_prompt=prompts[strategy_type],
        )
        self.strategy_type = strategy_type

    def _get_current_conditions(self, market: dict) -> dict:
        """Извлечь текущие рыночные условия для поиска warnings."""
        indicators = market.get("indicators", {})
        market.get("quote", {})
        news = market.get("news_briefing", {})

        rsi = indicators.get("RSI")
        if rsi is not None:
            if rsi < 30:
                rsi_bucket = "oversold"
            elif rsi < 45:
                rsi_bucket = "low"
            elif rsi < 55:
                rsi_bucket = "neutral"
            elif rsi < 70:
                rsi_bucket = "high"
            else:
                rsi_bucket = "overbought"
        else:
            rsi_bucket = None

        volatility = indicators.get("volatility_regime", indicators.get("volatility", "medium"))
        if isinstance(volatility, dict):
            volatility = volatility.get("regime", "medium")

        trend = indicators.get("trend", "sideways")
        if isinstance(trend, dict):
            trend = trend.get("direction", "sideways")

        sentiment = news.get("overall_sentiment", news.get("sentiment", {}))
        if isinstance(sentiment, str):
            sentiment_label = sentiment
        elif isinstance(sentiment, dict):
            sentiment_label = sentiment.get("label", sentiment.get("sentiment", "neutral"))
        else:
            sentiment_label = "neutral"

        return {
            "rsi_bucket": rsi_bucket,
            "volatility_regime": volatility,
            "trend": trend,
            "sentiment_label": sentiment_label,
        }

    def _rule_based_proposal(self, market: dict, news: dict) -> dict:
        """Rule-based proposal when LLM fails. Uses indicators to generate signals."""
        quote = market.get("quote", {})
        indicators = market.get("indicators", {})
        current_price = quote.get("last", 0) or quote.get("ask", 0) or quote.get("bid", 0)

        rsi = indicators.get("RSI", 50)
        macd = indicators.get("MACD", {})
        macd_hist = macd.get("histogram", 0) if isinstance(macd, dict) else 0
        trend = indicators.get("trend", "neutral")
        if isinstance(trend, dict):
            trend = trend.get("direction", "neutral")
        bb = indicators.get("BB", {})
        bb_lower = bb.get("lower", 0) if isinstance(bb, dict) else 0
        bb_upper = bb.get("upper", 999) if isinstance(bb, dict) else 999
        indicators.get("ATR", 0)

        # Support/resistance from market snapshot
        support = market.get("support", 0)
        resistance = market.get("resistance", 0)

        # News sentiment
        news_data = news.get("overall_sentiment", news.get("sentiment", {}))
        if isinstance(news_data, dict):
            sentiment_score = news_data.get("score", 0)
        elif isinstance(news_data, str):
            sentiment_score = 0.1 if "positive" in news_data else -0.1 if "negative" in news_data else 0
        else:
            sentiment_score = 0

        action = "HOLD"
        confidence = 0.0
        rationale = ""
        sl = 0
        tp = 0

        if self.strategy_type == "trend":
            # Trend: follow momentum
            if trend == "bullish" and macd_hist > 0 and rsi < 65:
                action = "LONG_OPEN"
                confidence = 0.5
                sl = round(support if support > 0 and support < current_price else current_price * 0.97, 2)
                tp = round(resistance if resistance > 0 and resistance > current_price else current_price * 1.05, 2)
                rationale = f"Trend bullish, MACD positive ({macd_hist:.3f}), RSI={rsi:.1f}"
            elif trend == "bearish" and macd_hist < 0 and rsi > 35:
                action = "SHORT_OPEN"
                confidence = 0.5
                sl = round(resistance if resistance > 0 and resistance > current_price else current_price * 1.03, 2)
                tp = round(support if support > 0 and support < current_price else current_price * 0.95, 2)
                rationale = f"Trend bearish, MACD negative ({macd_hist:.3f}), RSI={rsi:.1f}"
            else:
                action = "HOLD"
                rationale = f"No clear trend signal: trend={trend}, MACD={macd_hist:.3f}, RSI={rsi:.1f}"

        elif self.strategy_type == "contrarian":
            # Contrarian: buy oversold, sell overbought
            if rsi < 35 and (sentiment_score < -0.1 or current_price <= bb_lower * 1.01):
                action = "LONG_OPEN"
                confidence = 0.5
                sl = round(current_price * 0.96, 2)
                tp = round(current_price * 1.08, 2)
                rationale = f"Contrarian LONG: RSI oversold ({rsi:.1f}), sentiment negative"
            elif rsi > 65 and (sentiment_score > 0.1 or current_price >= bb_upper * 0.99):
                action = "SHORT_OPEN"
                confidence = 0.5
                sl = round(current_price * 1.04, 2)
                tp = round(current_price * 0.92, 2)
                rationale = f"Contrarian SHORT: RSI overbought ({rsi:.1f}), sentiment positive"
            else:
                action = "HOLD"
                rationale = f"No contrarian signal: RSI={rsi:.1f}, sentiment={sentiment_score:.2f}"

        elif self.strategy_type == "bearish":
            # Bearish: short when weakness confirmed
            if (trend == "bearish" or macd_hist < 0) and rsi > 40:
                action = "SHORT_OPEN"
                confidence = 0.45
                sl = round(resistance if resistance > 0 and resistance > current_price else current_price * 1.03, 2)
                tp = round(support if support > 0 and support < current_price else current_price * 0.93, 2)
                rationale = f"Bearish: trend={trend}, MACD={macd_hist:.3f}, RSI={rsi:.1f}"
            else:
                action = "HOLD"
                rationale = f"No bearish signal: trend={trend}, RSI={rsi:.1f}"

        # Ensure SL/TP are valid
        if action in ("LONG_OPEN", "SHORT_OPEN"):
            if sl <= 0 or tp <= 0 or sl == tp:
                sl = round(current_price * 0.97, 2) if action == "LONG_OPEN" else round(current_price * 1.03, 2)
                tp = round(current_price * 1.05, 2) if action == "LONG_OPEN" else round(current_price * 0.95, 2)

        return {
            "action": action,
            "confidence": confidence,
            "rationale": rationale,
            "suggested_stop_loss": sl,
            "suggested_take_profit": tp,
        }

    def process(self, input_data: dict) -> dict:
        """Обработка: генерация торгового предложения.

        input_data: {
            "news_briefing": {...},
            "market_snapshot": {...},
            "ticker": "SBER",
            "current_positions": [...]  -- текущие позиции по тикеру
        }
        """
        ticker = input_data.get("ticker", "")
        news = input_data.get("news_briefing", {})
        market = input_data.get("market_snapshot", {})
        current_positions = input_data.get("current_positions", [])

        # ── Learning: Получаем предупреждения из истории ──
        warnings_text = ""
        try:
            current_conditions = self._get_current_conditions(market)

            warnings = memory_tools.get_relevant_warnings(
                ticker=ticker,
                strategy=self.strategy_type,
                current_conditions=current_conditions,
                limit=5,
            )

            critical = memory_tools.get_critical_blocks(
                ticker=ticker,
                strategy=self.strategy_type,
            )

            if critical:
                warnings_text = "\n\n!!! CRITICAL BLOCK — DO NOT TRADE !!!\n"
                for block in critical:
                    warnings_text += f"- {block.get('pattern_description', 'Unknown pattern')}\n"
                    warnings_text += f"  Win rate: {block.get('win_rate', 0)}% over {block.get('times_observed', 0)} trades\n"
                warnings_text += "\nYou MUST return HOLD for this ticker+strategy combination.\n"

            elif warnings:
                warnings_text = "\n\nHISTORICAL LOSS WARNINGS:\n"
                for w in warnings:
                    sev = w.get("severity", "info").upper()
                    wr = w.get("win_rate", 0)
                    desc = w.get("pattern_description", "Unknown pattern")
                    times = w.get("times_lost", 0)
                    warnings_text += f"- [{sev}] {desc} (win rate: {wr}%, lost {times}x)\n"
                warnings_text += "\nConsider avoiding similar trades or significantly reducing confidence.\n"

        except Exception as e:
            logger.warning(f"Failed to get warnings for {ticker}/{self.strategy_type}: {e}")

        # ── Позиции: контекст для LLM ──
        positions_text = ""
        if current_positions:
            positions_text = "\n\nCURRENT POSITIONS:\n"
            for pos in current_positions:
                side = pos.get("side", "?")
                qty = pos.get("quantity", 0)
                entry = pos.get("entry_price", 0)
                sl = pos.get("stop_loss", 0)
                tp = pos.get("take_profit", 0)
                opened = pos.get("opened_at", "")[:16]
                positions_text += (
                    f"- {side} {qty} shares @ {entry:.2f} "
                    f"(SL={sl:.2f}, TP={tp:.2f}, opened={opened})\n"
                )
            positions_text += (
                "\nYou have existing positions in this ticker. "
                "You can propose CLOSE_LONG or CLOSE_SHORT to exit a position "
                "if conditions warrant it (e.g. take profit, cut loss, or signal reversal).\n"
                "Include 'closing_trade_id' in your proposal with the trade_id of the position to close.\n"
            )
        else:
            positions_text = (
                "\n\nNo current positions in this ticker. "
                "You can propose LONG_OPEN or SHORT_OPEN.\n"
            )

        prompt = f"""Generate a trade proposal for {ticker}.

NEWS BRIEFING:
{json.dumps(news, ensure_ascii=False, indent=2)}

MARKET DATA SNAPSHOT:
{json.dumps(market, ensure_ascii=False, indent=2)}
{positions_text}
{warnings_text}
Analyze the data and generate a trade proposal.

IMPORTANT: Return ONLY a filled-in JSON object with real values. Do NOT return templates or placeholders.

Example of correct output (use this exact structure with YOUR actual values):
{{"action": "LONG_OPEN", "confidence": 0.85, "rationale": "RSI oversold at 30, price near support 319", "suggested_stop_loss": 315.0, "suggested_take_profit": 330.0}}

Your JSON must contain: action, confidence (0.0-1.0), rationale, suggested_stop_loss, suggested_take_profit."""

        try:
            proposal = self._call_llm(prompt)
            # Check if LLM returned empty/invalid
            if not proposal or not isinstance(proposal, dict) or not proposal.get("action"):
                raise ValueError("LLM returned empty/invalid proposal")
        except Exception as e:
            logger.warning(f"Strategy LLM failed for {self.strategy_type}, using rule-based fallback: {e}")
            proposal = self._rule_based_proposal(market, news)

        # Гарантируем наличие обязательных полей
        proposal_id = str(uuid.uuid4())

        # Валидация SL/TP относительно текущей цены
        quote = market.get("quote", {})
        current_price = quote.get("last", 0) or quote.get("ask", 0) or quote.get("bid", 0)
        sl = proposal.get("suggested_stop_loss", 0)
        tp = proposal.get("suggested_take_profit", 0)
        action = proposal.get("action", "HOLD")

        # ── Programmatic validation: LLM output проверяется на соответствие данным ──
        ALLOWED_ACTIONS = {
            "trend":     {"LONG_OPEN", "SHORT_OPEN", "CLOSE_LONG", "CLOSE_SHORT", "HOLD"},
            "contrarian": {"LONG_OPEN", "SHORT_OPEN", "CLOSE_LONG", "CLOSE_SHORT", "HOLD"},
            "bearish":   {"SHORT_OPEN", "CLOSE_LONG", "CLOSE_SHORT", "HOLD"},
        }
        allowed = ALLOWED_ACTIONS.get(self.strategy_type, ALLOWED_ACTIONS["trend"])

        # 1. Action в допустимом списке
        if action not in allowed:
            logger.warning(f"[{self.strategy_type}] Invalid action '{action}' → HOLD")
            action = "HOLD"
            proposal["action"] = "HOLD"
            proposal["confidence"] = 0

        # 2. Confidence в диапазоне [0, 1]
        confidence = proposal.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            proposal["confidence"] = 0.0

        # 3. SL/TP проверка направления для OPEN
        if action == "LONG_OPEN" and current_price > 0:
            if sl >= current_price:
                sl = round(current_price * 0.97, 2)
                proposal["suggested_stop_loss"] = sl
            if tp <= current_price:
                tp = round(current_price * 1.05, 2)
                proposal["suggested_take_profit"] = tp
        elif action == "SHORT_OPEN" and current_price > 0:
            if sl <= current_price:
                sl = round(current_price * 1.03, 2)
                proposal["suggested_stop_loss"] = sl
            if tp >= current_price:
                tp = round(current_price * 0.95, 2)
                proposal["suggested_take_profit"] = tp

        # 4. R/R ratio >= 1.5
        sl = proposal.get("suggested_stop_loss", 0)
        tp = proposal.get("suggested_take_profit", 0)
        if action in ("LONG_OPEN", "SHORT_OPEN") and sl > 0 and tp > 0 and current_price > 0:
            risk = abs(current_price - sl)
            reward = abs(tp - current_price)
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < 1.5:
                    logger.warning(
                        f"[{self.strategy_type}] R/R too low: {rr_ratio:.2f} < 1.5 → HOLD"
                    )
                    action = "HOLD"
                    proposal["action"] = "HOLD"
                    proposal["confidence"] = 0
                    proposal["rationale"] = f"R/R {rr_ratio:.2f} below minimum 1.5. {proposal.get('rationale', '')}"

        # 5. SL/TP должны быть положительными числами
        if action in ("LONG_OPEN", "SHORT_OPEN"):
            if not sl or sl <= 0 or not tp or tp <= 0:
                logger.warning(f"[{self.strategy_type}] Missing SL/TP → HOLD")
                action = "HOLD"
                proposal["action"] = "HOLD"
                proposal["confidence"] = 0

        # Для CLOSE — находим trade_id позиции
        closing_trade_id = None
        if proposal.get("action") in ("CLOSE_LONG", "CLOSE_SHORT"):
            closing_trade_id = proposal.get("closing_trade_id")
            if not closing_trade_id and current_positions:
                # Если LLM не указал trade_id — берём первую позицию
                closing_trade_id = current_positions[0].get("trade_id")

        result = self._format_message("trade_proposal", {
            "id": proposal_id,
            "ticker": ticker,
            "action": proposal.get("action", "HOLD"),
            "confidence": min(max(proposal.get("confidence", 0.0), 0.0), 1.0),
            "rationale": proposal.get("rationale", "No rationale provided"),
            "suggested_stop_loss": proposal.get("suggested_stop_loss", 0),
            "suggested_take_profit": proposal.get("suggested_take_profit", 0),
            "strategy": self.strategy_type,
            "closing_trade_id": closing_trade_id,
        })

        self.log_action(
            input_data={"ticker": ticker, "strategy": self.strategy_type},
            output_data=result,
            tool_calls=["llm_generate"],
        )

        return result


class StrategyAgentGroup:
    """Группа стратегических агентов."""

    def __init__(self, llm_client):
        self.agents = [
            StrategyAgent(llm_client, strategy_type="trend"),
            StrategyAgent(llm_client, strategy_type="contrarian"),
            StrategyAgent(llm_client, strategy_type="bearish"),
        ]

    def process(self, input_data: dict) -> list[dict]:
        """Все стратеги анализируют данные и возвращают предложения (параллельно)."""
        ticker = input_data.get("ticker", "")
        if ticker:
            try:
                input_data["ticker"] = validate_ticker(ticker)
            except ValueError as e:
                logger.error(f"Invalid ticker in strategy input: {e}")
                return []

        import concurrent.futures

        def _run_agent(agent):
            try:
                return agent.process(input_data)
            except Exception as e:
                logger.error(f"Strategy agent {agent.name} failed: {e}")
                return None

        proposals = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_run_agent, agent): agent for agent in self.agents}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result and result.get("action") != "HOLD":
                    proposals.append(result)

        # Сортируем по уверенности
        proposals.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return proposals
