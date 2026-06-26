"""Тест модуля обучения на убытках."""
import sys
import os
import io
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.memory import (
    init_db, store_trade_context, get_trade_context,
    _extract_conditions, analyze_loss_pattern, get_strategy_performance,
    store_lesson, get_relevant_warnings, get_critical_blocks,
)

def main():
    logger.info("=== Learning Module Test ===\n")

    # 1. Init DB
    init_db()
    logger.info("[OK] DB initialized with new tables\n")

    # 2. Store trade context
    trade_id = "test-001"
    market = {
        "indicators": {
            "rsi": 72,
            "macd": {"signal": "bearish"},
            "bollinger": {"position": "above_upper"},
            "volatility_regime": "high",
            "trend": "downtrend",
            "atr": 15.5,
            "avg_volume": 1000000,
        },
        "quote": {"price": 280.0, "volume": 1500000, "high": 285, "low": 275},
    }
    news = {"overall_sentiment": {"score": -0.3, "label": "negative"}}

    ok = store_trade_context(trade_id, "SBER", market, news)
    logger.info("[%s] Store trade context", "OK" if ok else "FAIL")

    # 3. Get trade context
    ctx = get_trade_context(trade_id)
    assert ctx.get("rsi") == 72, f"RSI mismatch: {ctx.get('rsi')}"
    assert ctx.get("sentiment_label") == "negative", f"Sentiment mismatch: {ctx.get('sentiment_label')}"
    assert ctx.get("volatility_regime") == "high", f"Volatility mismatch"
    assert ctx.get("trend") == "downtrend", f"Trend mismatch"
    logger.info("[OK] Get trade context: RSI=%s, sentiment=%s, vol=%s\n", ctx.get('rsi'), ctx.get('sentiment_label'), ctx.get('volatility_regime'))

    # 4. Extract conditions
    conditions = _extract_conditions(ctx)
    assert conditions.get("rsi_bucket") == "overbought", f"RSI bucket wrong: {conditions.get('rsi_bucket')}"
    assert conditions.get("sentiment_label") == "negative"
    logger.info("[OK] Extract conditions: %s\n", conditions)

    # 5. Store lessons
    lesson1 = {
        "trade_id": "test-001",
        "ticker": "SBER",
        "strategy": "bearish",
        "lesson_type": "pattern",
        "pattern_description": "SHORT SBER when RSI > 70 + negative sentiment - lost 4/5 times",
        "conditions": {"rsi_bucket": "overbought", "sentiment_label": "negative", "volatility_regime": "high"},
        "confidence": 0.8,
        "times_observed": 5,
        "times_lost": 4,
        "win_rate": 20,
        "severity": "critical",
    }
    ok = store_lesson(lesson1)
    logger.info("[%s] Store critical lesson", "OK" if ok else "FAIL")

    lesson2 = {
        "trade_id": "test-002",
        "ticker": "SBER",
        "strategy": "trend",
        "lesson_type": "pattern",
        "pattern_description": "Trend strategy on SBER in high volatility - 40% win rate",
        "conditions": {"volatility_regime": "high", "trend": "downtrend"},
        "confidence": 0.6,
        "times_observed": 10,
        "times_lost": 6,
        "win_rate": 40,
        "severity": "warning",
    }
    ok = store_lesson(lesson2)
    logger.info("[%s] Store warning lesson\n", "OK" if ok else "FAIL")

    # 6. Get relevant warnings
    warnings = get_relevant_warnings(
        ticker="SBER",
        strategy="bearish",
        current_conditions={"rsi_bucket": "overbought", "sentiment_label": "negative"},
    )
    assert len(warnings) > 0, "No warnings found"
    logger.info("[OK] Get warnings: %s found", len(warnings))
    for w in warnings:
        logger.info("  - [%s] %s\n", w['severity'], w['pattern_description'])

    # 7. Get critical blocks
    blocks = get_critical_blocks(ticker="SBER", strategy="bearish")
    assert len(blocks) > 0, "No critical blocks found"
    logger.info("[OK] Get critical blocks: %s found", len(blocks))
    for b in blocks:
        logger.info("  - BLOCKED: %s\n", b['pattern_description'])

    # 8. Strategy performance (no data yet)
    perf = get_strategy_performance(ticker="SBER", strategy="trend")
    logger.info("[OK] Strategy performance: %s\n", perf)

    # 9. Analyze loss pattern (no trades in DB, should return empty)
    patterns = analyze_loss_pattern(ticker="SBER", strategy="bearish")
    logger.info("[OK] Analyze loss patterns: %s patterns found (expected 0 without trades)\n", len(patterns))

    logger.info("=== All tests passed! ===")

if __name__ == "__main__":
    main()
