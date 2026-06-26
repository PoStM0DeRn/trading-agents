"""Тестирование FinGPT модели через LM Studio API."""

import httpx
import json
import time

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:1234"
MODEL = "fingpt-mt-llama-3-8b-lora"


def chat(prompt: str, system: str = None, temperature: float = 0.3) -> str:
    """Отправить запрос к модели."""
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
            "max_tokens": 1024,
        },
        timeout=120.0,
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]


def test_sentiment():
    """Тест 1: Sentiment analysis на английских новостях."""
    logger.info("=" * 60)
    logger.info("TEST 1: Sentiment Analysis (English)")
    logger.info("=" * 60)

    system = "You are a financial sentiment analyst. Analyze the sentiment of the given financial news. Respond with positive, negative, or neutral and a brief explanation."

    headlines = [
        "Apple Inc. reported record quarterly earnings, beating analyst expectations by 15%.",
        "Tesla shares dropped 8% after the company announced delays in Cybertruck production.",
        "Sberbank maintains its dividend policy at 50% of net profit.",
        "Газпром сократил добычу газа на 15% из-за снижения спроса в Европе.",
        "Сбербанк увеличил чистую прибыль на 20% в Q3 2025 года.",
    ]

    for i, headline in enumerate(headlines, 1):
        logger.info(f"\n--- Headline {i} ---")
        logger.info(f"Input: {headline}")
        start = time.time()
        result = chat(headline, system=system)
        elapsed = time.time() - start
        logger.info(f"Output: {result}")
        logger.info(f"Time: {elapsed:.1f}s")


def test_forecaster():
    """Тест 2: Stock prediction / forecasting."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Stock Forecasting")
    logger.info("=" * 60)

    system = "You are a seasoned stock market analyst. Provide analysis and prediction for the stock."

    prompts = [
        """Analyze Sberbank (MOEX: SBER) based on the following information:
- Current price: 320 RUB
- RSI: 40 (approaching oversold)
- MACD: bullish crossover
- News: Sberbank reported 20% increase in net profit for Q3 2025
- Dividend yield: 5.2%
- Oil prices rising, supporting ruble

Provide your analysis and prediction for the next week.""",

        """Проанализируйте акции Газпрома (MOEX: GAZP):
- Текущая цена: 170 RUB
- RSI: 55 (нейтральная зона)
- Новости: Газпром сократил экспорт газа на 15%
- Газовые цены в Европе выросли на 10%
- Дивидендная доходность: 8.1%

Дайте анализ и прогноз на следующую неделю.""",
    ]

    for i, prompt in enumerate(prompts, 1):
        logger.info(f"\n--- Forecast {i} ---")
        logger.info(f"Input:\n{prompt}")
        start = time.time()
        result = chat(prompt, system=system)
        elapsed = time.time() - start
        logger.info(f"\nOutput:\n{result}")
        logger.info(f"Time: {elapsed:.1f}s")


def test_trading_decision():
    """Тест 3: Торговое решение на основе данных."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Trading Decision")
    logger.info("=" * 60)

    system = """You are a professional stock trader. Based on the provided market data, 
decide whether to BUY, SELL, or HOLD the stock. Provide your reasoning."""

    prompt = """Trading signal for SBER (Sberbank):

MARKET DATA:
- Price: 315 RUB
- 52-week range: 250-380 RUB
- Volume: 15M (above average)

TECHNICAL INDICATORS:
- RSI(14): 35 (oversold)
- MACD: negative but narrowing
- SMA50: 325 (price below)
- SMA200: 310 (price above)
- Bollinger: near lower band

NEWS SENTIMENT:
- Positive: Strong Q3 earnings, dividend expectations
- Negative: Western sanctions concerns, ruble volatility

FUNDAMENTALS:
- P/E: 5.2
- P/B: 0.8
- Dividend yield: 5.5%
- Market cap: 7.5T RUB

Should I BUY, SELL, or HOLD? Provide detailed analysis and confidence level (0-100%)."""

    logger.info(f"Input:\n{prompt}")
    start = time.time()
    result = chat(prompt, system=system)
    elapsed = time.time() - start
    logger.info(f"\nOutput:\n{result}")
    logger.info(f"Time: {elapsed:.1f}s")


def test_russian_news():
    """Тест 4: Анализ русскоязычных новостей."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Russian News Analysis")
    logger.info("=" * 60)

    system = "Проанализируйте финансовую новость. Определите sentiment (positive/negative/neutral) и влияние на акции компании."

    news = [
        "Сбербанк объявил о выкупе акций на сумму до 100 млрд рублей",
        "Газпром зафиксировал рекордный экспорт газа в Китай",
        "Лукойл увеличил добычу нефти на 5% в ноябре 2025 года",
        "Яндекс объявил о запуске нового AI-продукта для бизнеса",
        "ВТБ снизил ставки по ипотеке до рекордного минимума 18.5%",
    ]

    for i, headline in enumerate(news, 1):
        logger.info(f"\n--- News {i} ---")
        logger.info(f"Input: {headline}")
        start = time.time()
        result = chat(headline, system=system)
        elapsed = time.time() - start
        logger.info(f"Output: {result}")
        logger.info(f"Time: {elapsed:.1f}s")


def test_json_output():
    """Тест 5: Структурированный JSON вывод."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Structured JSON Output")
    logger.info("=" * 60)

    system = """You are a financial analysis API. Always respond with valid JSON only.
No text before or after the JSON object."""

    prompt = """Analyze this trading opportunity and return JSON:

Stock: SBER (Sberbank)
Price: 315 RUB
RSI: 35 (oversold)
News sentiment: Positive (strong earnings)
Dividend yield: 5.5%

Return JSON with these fields:
{
  "ticker": "SBER",
  "action": "BUY/SELL/HOLD",
  "confidence": 0-100,
  "entry_price": number,
  "stop_loss": number,
  "take_profit": number,
  "risk_reward_ratio": number,
  "reasoning": "string"
}"""

    logger.info(f"Input:\n{prompt}")
    start = time.time()
    result = chat(prompt, system=system)
    elapsed = time.time() - start
    logger.info(f"\nOutput:\n{result}")
    logger.info(f"Time: {elapsed:.1f}s")

    # Try to parse JSON
    try:
        # Try direct parse
        parsed = json.loads(result)
        logger.info(f"\nJSON parsed successfully!")
        logger.info(json.dumps(parsed, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        # Try to extract JSON from response
        import re
        match = re.search(r'\{[\s\S]*\}', result)
        if match:
            try:
                parsed = json.loads(match.group())
                logger.info(f"\nJSON extracted and parsed!")
                logger.info(json.dumps(parsed, indent=2, ensure_ascii=False))
            except:
                logger.info("\nFailed to parse JSON from response")
        else:
            logger.info("\nNo JSON found in response")


if __name__ == "__main__":
    logger.info("FinGPT Model Testing")
    logger.info(f"Model: {MODEL}")
    logger.info(f"Endpoint: {BASE_URL}")
    logger.info()

    test_sentiment()
    test_forecaster()
    test_trading_decision()
    test_russian_news()
    test_json_output()

    logger.info("\n" + "=" * 60)
    logger.info("ALL TESTS COMPLETE")
    logger.info("=" * 60)
