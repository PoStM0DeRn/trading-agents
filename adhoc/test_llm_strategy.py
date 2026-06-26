"""Test LLM JSON generation with strategy-like prompt."""
import sys
import os
import io
import json
import logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from integrations.lmstudio_client import LMStudioClient

client = LMStudioClient()

prompt = """You are a trend-following strategy agent. Analyze SBER stock.

Current price: 301.10 RUB
RSI: 26.88 (oversold)
MACD: bearish
Trend: bearish
Sentiment: 0.8 positive, 0.2 neutral

Generate a trade proposal. Respond ONLY with JSON:
{"action": "LONG_OPEN or SHORT_OPEN or CLOSE_LONG or CLOSE_SHORT or HOLD", "confidence": 0.0-1.0, "rationale": "...", "suggested_stop_loss": number, "suggested_take_profit": number}"""

result = client.generate_json(prompt, system="You are a trading strategy. Output valid JSON only. No thinking, no explanation.")
logger.info("Result: %s", json.dumps(result, indent=2, ensure_ascii=False))
