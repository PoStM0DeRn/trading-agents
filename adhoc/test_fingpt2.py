"""Дополнительные тесты FinGPT - поиск оптимального формата промптов."""

import httpx
import json
import time

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:1234"
MODEL = "fingpt-mt-llama-3-8b-lora"


def chat(prompt: str, system: str = None, temperature: float = 0.3, max_tokens: int = 512) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=120.0,
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]


def test_short_prompts():
    """Тест: Короткие промпты для sentiment."""
    logger.info("=" * 60)
    logger.info("TEST A: Short Sentiment Prompts")
    logger.info("=" * 60)

    system = "Classify the sentiment of this financial text as positive, negative, or neutral."

    tests = [
        "Sberbank profit up 20%",
        "Tesla stock crashes 15%",
        "Apple maintains flat earnings",
        "Oil prices surge 10%",
        "Ruble weakens against dollar",
    ]

    for text in tests:
        logger.info(f"\nInput: {text}")
        result = chat(text, system=system)
        logger.info(f"Output: {result}")


def test_instruction_format():
    """Тест: Формат инструкций как в FinGPT."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST B: Instruction Format (FinGPT style)")
    logger.info("=" * 60)

    tests = [
        {
            "instruction": "What is the sentiment of this news? Please choose an answer from {negative/neutral/positive}.",
            "input": "Sberbank reports record profit for Q3 2025"
        },
        {
            "instruction": "Does the news headline talk about price going up? Please choose an answer from {Yes/No}.",
            "input": "Tesla shares surge 10% on strong earnings"
        },
        {
            "instruction": "Extract the main financial entity and its sentiment from this text.",
            "input": "Gazprom reduces gas exports to Europe by 15%"
        },
    ]

    for test in tests:
        prompt = f"{test['instruction']}\n\nInput: {test['input']}"
        logger.info(f"\nInput:\n{prompt}")
        result = chat(prompt)
        logger.info(f"Output: {result}")


def test_multi_choice():
    """Тест: Множественный выбор."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST C: Multiple Choice")
    logger.info("=" * 60)

    system = "Answer with the option letter only."

    tests = [
        "Q: Sberbank dividend yield is 5.5%, P/E is 5.2. Is this stock undervalued or overvalued?\nA) Undervalued  B) Overvalued  C) Fairly valued",
        "Q: Oil price rises 10%. Impact on Gazprom stock?\nA) Positive  B) Negative  C) No impact",
        "Q: RSI is 35 (oversold). Technical signal?\nA) Buy  B) Sell  C) Neutral",
    ]

    for q in tests:
        logger.info(f"\nInput: {q}")
        result = chat(q, system=system)
        logger.info(f"Output: {result}")


def test_json_formats():
    """Тест: Разные JSON форматы."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST D: JSON Output Formats")
    logger.info("=" * 60)

    system = "Respond with valid JSON only."

    tests = [
        # Simple sentiment
        'Analyze sentiment: "Sberbank profit up 20%". Return: {"sentiment": "...", "confidence": 0-100}',

        # Trading signal
        '''Stock: SBER, Price: 315, RSI: 35. Return JSON:
{"action": "BUY/SELL/HOLD", "confidence": 0-100, "stop_loss": price, "take_profit": price}''',

        # Multi-stock comparison
        '''Compare stocks and return JSON:
{"winner": "ticker", "reasoning": "...", "stocks": {"SBER": {"score": 0-100}, "GAZP": {"score": 0-100}}}''',
    ]

    for test in tests:
        logger.info(f"\nInput:\n{test}")
        result = chat(test, system=system)
        logger.info(f"\nOutput:\n{result}")
        # Try parse
        try:
            parsed = json.loads(result)
            logger.info("JSON OK!")
        except:
            import re
            match = re.search(r'\{[\s\S]*\}', result)
            if match:
                try:
                    json.loads(match.group())
                    logger.info("JSON extracted OK!")
                except:
                    logger.info("JSON parse failed")
            else:
                logger.info("No JSON found")


def test_trading_signals_batch():
    """Тест: Пакетный анализ сигналов."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST E: Batch Trading Signals")
    logger.info("=" * 60)

    system = "You are a trading signal generator. For each stock, output a JSON object with action and confidence."

    prompt = '''Analyze these 3 stocks and output a JSON array with trading signals:

1. SBER: Price 315, RSI 35, Positive earnings news
2. GAZP: Price 170, RSI 55, Mixed sentiment
3. LKOH: Price 7500, RSI 72, Oil prices rising

Output format:
[
  {"ticker": "SBER", "action": "BUY/SELL/HOLD", "confidence": 0-100},
  {"ticker": "GAZP", "action": "BUY/SELL/HOLD", "confidence": 0-100},
  {"ticker": "LKOH", "action": "BUY/SELL/HOLD", "confidence": 0-100}
]'''

    logger.info(f"Input:\n{prompt}")
    result = chat(prompt, system=system)
    logger.info(f"\nOutput:\n{result}")

    # Parse
    try:
        parsed = json.loads(result)
        logger.info(f"\nParsed {len(parsed)} signals:")
        for s in parsed:
            logger.info(f"  {s.get('ticker')}: {s.get('action')} ({s.get('confidence')}%)")
    except:
        import re
        match = re.search(r'\[[\s\S]*\]', result)
        if match:
            try:
                parsed = json.loads(match.group())
                logger.info(f"\nExtracted {len(parsed)} signals")
            except:
                logger.info("Parse failed")


if __name__ == "__main__":
    logger.info("FinGPT Additional Tests")
    logger.info(f"Model: {MODEL}")
    logger.info()

    test_short_prompts()
    test_instruction_format()
    test_multi_choice()
    test_json_formats()
    test_trading_signals_batch()

    logger.info("\n" + "=" * 60)
    logger.info("ALL ADDITIONAL TESTS COMPLETE")
    logger.info("=" * 60)
