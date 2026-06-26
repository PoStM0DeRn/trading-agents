"""Market Data Agent — сбор и анализ рыночных данных с microstructure, correlations, patterns, corporate, advanced."""

import logging
from datetime import datetime, timezone

import numpy as np

from agents.base_agent import BaseAgent
from tools import market_data as md_tools
from tools import microstructure as micro_tools
from tools import correlations as corr_tools
from tools import patterns as pattern_tools
from tools import corporate as corp_tools
from tools import fundamentals as fund_tools
from tools import advanced_analysis as adv_tools
from tools.prompts import load_prompt

logger = logging.getLogger(__name__)


def _sanitize(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj




class MarketDataAgent(BaseAgent):
    """Агент рыночных данных — полный анализ MOEX акций."""

    def __init__(self, llm_client, tools: dict = None):
        super().__init__(
            name="MarketData",
            llm_client=llm_client,
            system_prompt=load_prompt("market_data"),
            tools=self._build_tools({
                "get_current_quote": md_tools.get_current_quote,
                "get_historical_data": md_tools.get_historical_data,
                "get_technical_indicators": md_tools.get_technical_indicators,
                "get_support_resistance_levels": md_tools.get_support_resistance_levels,
                "get_volatility": md_tools.get_volatility,
                "get_order_book_imbalance": micro_tools.get_order_book_imbalance,
                "get_volume_pressure": micro_tools.get_volume_pressure,
                "get_obv": micro_tools.get_obv,
                "get_volume_profile": micro_tools.get_volume_profile,
                "get_brent_correlation": corr_tools.get_brent_correlation,
                "get_usdrub_correlation": corr_tools.get_usdrub_correlation,
                "get_market_context": corr_tools.get_market_context,
                "get_candlestick_patterns": pattern_tools.get_candlestick_patterns,
                "get_dividend_calendar": corp_tools.get_dividend_calendar,
                "get_instrument_info": corp_tools.get_instrument_info,
                "get_trading_status": corp_tools.get_trading_status,
                "get_fundamentals": fund_tools.get_fundamentals,
                "get_valuation_signal": fund_tools.get_valuation_signal,
                "get_ichimoku": adv_tools.get_ichimoku,
                "get_fibonacci_levels": adv_tools.get_fibonacci_levels,
                "get_adx": adv_tools.get_adx,
                "get_advanced_snapshot": adv_tools.get_advanced_snapshot,
            }, tools),
        )

    def process(self, input_data: dict) -> dict:
        """Полный анализ: quote + indicators + microstructure + correlations + patterns + corporate.

        input_data: {"ticker": "SBER", "period": "3mo"}
        """
        ticker = input_data.get("ticker", "")
        period = input_data.get("period", "3mo")

        # --- 1. Quote + Technical Indicators ---
        quote = self._call_tool("get_current_quote", ticker=ticker)
        indicators = self._call_tool(
            "get_technical_indicators", ticker=ticker,
            indicators=["RSI", "MACD", "BB", "ATR"], period=period,
        )
        levels = self._call_tool("get_support_resistance_levels", ticker=ticker, period=period)
        volatility = self._call_tool("get_volatility", ticker=ticker, period="1mo")

        # --- 2. Microstructure ---
        microstructure = {}
        # Order book doesn't need period
        try:
            microstructure["order_book_imbalance"] = self._call_tool("get_order_book_imbalance", ticker=ticker)
        except Exception as e:
            logger.warning(f"Microstructure order_book_imbalance failed: {e}")
            microstructure["order_book_imbalance"] = {"error": str(e)}

        for fn_name in ["get_volume_pressure", "get_obv", "get_volume_profile"]:
            try:
                microstructure[fn_name.replace("get_", "")] = self._call_tool(fn_name, ticker=ticker, period=period)
            except Exception as e:
                logger.warning(f"Microstructure {fn_name} failed: {e}")
                microstructure[fn_name.replace("get_", "")] = {"error": str(e)}

        # --- 3. Correlations ---
        correlations = {}
        for fn_name in ["get_brent_correlation", "get_usdrub_correlation"]:
            try:
                key = fn_name.replace("get_", "").replace("_correlation", "")
                correlations[key] = self._call_tool(fn_name, ticker=ticker, period=period)
            except Exception as e:
                logger.warning(f"Correlation {fn_name} failed: {e}")
                correlations[fn_name.replace("get_", "")] = {"error": str(e)}

        # --- 4. Candlestick Patterns ---
        patterns = {}
        try:
            patterns = self._call_tool("get_candlestick_patterns", ticker=ticker, period=period)
        except Exception as e:
            logger.warning(f"Patterns failed: {e}")
            patterns = {"error": str(e)}

        # --- 5. Corporate Events ---
        corporate = {}
        for fn_name in ["get_dividend_calendar", "get_instrument_info", "get_trading_status"]:
            try:
                corporate[fn_name.replace("get_", "")] = self._call_tool(fn_name, ticker=ticker)
            except Exception as e:
                logger.warning(f"Corporate {fn_name} failed: {e}")
                corporate[fn_name.replace("get_", "")] = {"error": str(e)}

        # --- 5b. Fundamentals ---
        fundamentals = {}
        try:
            fund = self._call_tool("get_fundamentals", ticker=ticker)
            fundamentals = fund
            if fund.get("pe_ratio"):
                valuation = self._call_tool(
                    "get_valuation_signal",
                    pe_ratio=fund["pe_ratio"],
                    pb_ratio=fund.get("pb_ratio", 1.0),
                    dividend_yield=fund.get("dividend_yield", 0),
                )
                fundamentals["valuation"] = valuation
        except Exception as e:
            logger.warning(f"Fundamentals failed: {e}")
            fundamentals = {"error": str(e)}

        # --- 6. Advanced Analysis (Ichimoku, Fibonacci, ADX) ---
        advanced = {}
        for fn_name in ["get_ichimoku", "get_fibonacci_levels", "get_adx"]:
            try:
                key = fn_name.replace("get_", "")
                advanced[key] = self._call_tool(fn_name, ticker=ticker, period=period)
            except Exception as e:
                logger.warning(f"Advanced {fn_name} failed: {e}")
                advanced[key] = {"error": str(e)}

        # --- 7. Rule-based Analysis (deterministic, no LLM needed) ---
        rsi = indicators.get("RSI", 50)
        macd = indicators.get("MACD", {})
        macd_hist = macd.get("histogram", 0) if isinstance(macd, dict) else 0
        adx_data = advanced.get("adx", {})
        adx_val = adx_data.get("adx", 0) if isinstance(adx_data, dict) else 0
        trend_dir = adx_data.get("trend_direction", "neutral") if isinstance(adx_data, dict) else "neutral"
        obv_data = microstructure.get("obv", {})
        obv_signal = obv_data.get("signal", "neutral") if isinstance(obv_data, dict) else "neutral"
        imbalance_data = microstructure.get("order_book_imbalance", {})
        imbalance_signal = imbalance_data.get("signal", "neutral") if isinstance(imbalance_data, dict) else "neutral"
        ichimoku = advanced.get("ichimoku", {})
        ich_trend = ichimoku.get("trend", "neutral") if isinstance(ichimoku, dict) else "neutral"

        # Trend determination
        bullish_score = 0
        bearish_score = 0
        if rsi < 40:
            bullish_score += 1
        elif rsi > 60:
            bearish_score += 1
        if macd_hist > 0:
            bullish_score += 1
        elif macd_hist < 0:
            bearish_score += 1
        if trend_dir == "bullish":
            bullish_score += 2
        elif trend_dir == "bearish":
            bearish_score += 2
        if obv_signal == "bullish":
            bullish_score += 1
        elif obv_signal == "bearish":
            bearish_score += 1
        if imbalance_signal == "bullish":
            bullish_score += 1
        elif imbalance_signal == "bearish":
            bearish_score += 1
        if ich_trend == "bullish":
            bullish_score += 1
        elif ich_trend == "bearish":
            bearish_score += 1

        total = bullish_score + bearish_score
        if total == 0:
            trend = "neutral"
            trend_strength = 0.5
        elif bullish_score > bearish_score:
            trend = "bullish"
            trend_strength = min(bullish_score / max(total, 1), 1.0)
        elif bearish_score > bullish_score:
            trend = "bearish"
            trend_strength = min(bearish_score / max(total, 1), 1.0)
        else:
            trend = "neutral"
            trend_strength = 0.5

        # Signals
        signals = []
        if rsi < 30:
            signals.append("RSI oversold")
        elif rsi > 70:
            signals.append("RSI overbought")
        if macd_hist > 0:
            signals.append("MACD bullish")
        elif macd_hist < 0:
            signals.append("MACD bearish")
        if obv_signal == "bearish":
            signals.append("OBV bearish divergence")
        if imbalance_signal == "bearish":
            signals.append("Order book bearish")
        if ich_trend == "bearish":
            signals.append("Ichimoku bearish")
        elif ich_trend == "bullish":
            signals.append("Ichimoku bullish")
        if adx_val > 25 and trend_dir == "bearish":
            signals.append("Strong bearish trend (ADX)")
        elif adx_val > 25 and trend_dir == "bullish":
            signals.append("Strong bullish trend (ADX)")

        # Entry signal
        if trend == "bullish" and rsi < 40:
            entry_signal = "buy"
        elif trend == "bearish" and rsi > 60:
            entry_signal = "sell"
        else:
            entry_signal = "hold"

        analysis = {
            "trend": trend,
            "signals": signals,
            "trend_strength": round(trend_strength, 2),
            "entry_signal": entry_signal,
        }

        # --- 8. Build snapshot ---
        snapshot = _sanitize(self._format_message("market_data_snapshot", {
            "ticker": ticker,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "quote": quote,
            "indicators": indicators,
            "support": levels.get("support", 0),
            "resistance": levels.get("resistance", 0),
            "volatility": volatility,
            "microstructure": microstructure,
            "correlations": correlations,
            "patterns": {
                "bullish": patterns.get("bullish_patterns", []),
                "bearish": patterns.get("bearish_patterns", []),
                "signal": patterns.get("signal", "neutral"),
            },
            "corporate": corporate,
            "fundamentals": fundamentals,
            "advanced": advanced,
            "trend": analysis.get("trend", "neutral"),
            "signals": analysis.get("signals", []),
            "trend_strength": analysis.get("trend_strength", 0.5),
            "entry_signal": analysis.get("entry_signal", "hold"),
        }))

        self.log_action(
            input_data=input_data,
            output_data=snapshot,
            tool_calls=[
                "get_current_quote", "get_technical_indicators",
                "get_support_resistance_levels", "get_volatility",
                "get_order_book_imbalance", "get_volume_pressure",
                "get_obv", "get_volume_profile",
                "get_brent_correlation", "get_usdrub_correlation",
                "get_candlestick_patterns",
                "get_dividend_calendar", "get_instrument_info", "get_trading_status",
                "get_ichimoku", "get_fibonacci_levels", "get_adx",
            ],
        )

        return snapshot
