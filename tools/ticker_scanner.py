"""LLM Ticker Scanner — динамический поиск и оценка акций MOEX через ИИ."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from integrations.moex_scanner import get_all_moex_shares
from config.secrets import secrets

logger = logging.getLogger(__name__)

# Глобальные клиенты (инжектируются при инициализации)
_llm_client = None
_client = None
_config = None

# ── Predefined sector mapping for MOEX tickers ──
TICKER_SECTORS = {
    # Oil & Gas
    "GAZP": "oil_gas", "LKOH": "oil_gas", "ROSN": "oil_gas", "NVTK": "oil_gas",
    "SNGS": "oil_gas", "SNGSP": "oil_gas", "TRNF": "oil_gas", "BANE": "oil_gas",
    "BANEP": "oil_gas", "ENRU": "oil_gas", "SIBN": "oil_gas",
    # Finance
    "SBER": "finance", "SBERP": "finance", "VTBR": "finance", "CBOM": "finance",
    "AKRN": "finance", "OHYO": "finance", "PRMB": "finance", "TCSG": "finance",
    "OZON": "finance", "OZONP": "finance",
    # Technology
    "YDEX": "technology", "VKCO": "technology", "MOD": "technology",
    # Mining
    "GMKN": "mining", "NLMK": "mining", "MOEX": "mining", "CHMF": "mining",
    "STEL": "mining", "MAGN": "mining", "MDMGP": "mining",
    # Energy
    "IRAO": "energy", "HYDR": "energy", "FEES": "energy", "OGKB": "energy",
    "TGKA": "energy", "TGKDP": "energy", "RSTF": "energy",
    # Telecom
    "MTSS": "telecom", "RTKM": "telecom", "RTKMP": "telecom",
    "FIVE": "telecom",
    # Retail
    "MGNT": "retail", "FIXP": "retail",
    # Pharma
    "RSTI": "pharma", "PHOR": "pharma", "OKEH": "pharma",
}

# ── Sector descriptions для LLM ──
SECTOR_DESCRIPTIONS = {
    "oil_gas": "Нефтегазовый сектор (GAZP, LKOH, ROSN, NVTK, BANE, SNGS, TRNF)",
    "finance": "Финансовый сектор (SBER, VTBR, CBOM, AKRN, OHYO, PRMB)",
    "technology": "Технологический сектор (YDEX, OZON, VKCO, TCSG, MOD)",
    "mining": "Горнодобывающий сектор (GMKN, NLMK, MOEX, CHMF, STEL, ENRU)",
    "energy": "Энергетический сектор (IRAO, HYDR, FEES, OGKB, TGKA)",
    "telecom": "Телекоммуникации (MTSS, RTKM, MGNT, FIVE)",
    "pharma": "Фармацевтика (RSTI, PHOR, OKEH)",
    "retail": "Розничная торговля (Magnit, Fix Price)",
    "other": "Другие сектора",
}

SCAN_PROMPT = """You are a professional MOEX stock analyst. Analyze these Russian stocks and select the BEST candidates for trading.

## Available Stocks ({total_count} total, showing {shown_count}):
{stocks_list}

## Current Portfolio Context:
- Open positions: {open_positions}
- Current capital: {capital:,.0f} RUB
- Allowed sectors: {allowed_sectors}

## Your Task:
Select the TOP {max_picks} stocks that are MOST promising for trading RIGHT NOW.

Consider:
1. **Volume & Liquidity** — stocks with high average daily volume are preferred
2. **Volatility** — moderate volatility (20-60% annual) is ideal for trading
3. **Sector Diversification** — don't pick all from same sector
4. **Avoid Overlap** — don't recommend stocks already in portfolio
5. **Recent Momentum** — stocks showing directional moves
6. **Risk/Reward** — look for stocks with clear technical setups

## Response Format (JSON ONLY):
{{
    "selected_tickers": [
        {{
            "ticker": "SBER",
            "reason": "Strong banking sector momentum, high liquidity",
            "score": 85,
            "sector": "finance",
            "risk_level": "medium"
        }},
        {{
            "ticker": "GAZP",
            "reason": "Energy sector recovery play, oversold on RSI",
            "score": 78,
            "sector": "oil_gas",
            "risk_level": "high"
        }}
    ],
    "market_outlook": "bullish/bearish/neutral",
    "reasoning": "Brief market reasoning"
}}

IMPORTANT: Respond with VALID JSON only. No text before or after."""


def set_clients(llm_client, tinvest_client, config: dict):
    """Инициализация клиентов для сканера."""
    global _llm_client, _client, _config
    _llm_client = llm_client
    _client = tinvest_client
    _config = config or {}


def scan_market(
    max_picks: int = 5,
    sectors: list[str] = None,
    min_volume: int = 0,
    open_positions: list[dict] = None,
    capital: float = 100000,
    use_llm: bool = True,
) -> dict:
    """Главный метод — сканирование рынка и выбор лучших тикеров.

    Args:
        max_picks: Максимальное количество тикеров для выбора
        sectors: Фильтр по секторам (None = все)
        min_volume: Минимальный средний объем
        open_positions: Текущие позиции портфеля
        capital: Текущий капитал
        use_llm: Использовать LLM для анализа (False = простая фильтрация)

    Returns:
        {
            "selected_tickers": [...],
            "all_candidates": [...],
            "market_outlook": "bullish/bearish/neutral",
            "scan_time": "ISO timestamp",
            "method": "llm" | "filter",
        }
    """
    if not _client:
        logger.error("T-Invest client not initialized")
        return {"error": "Client not connected", "selected_tickers": []}

    # 1. Получаем полный листинг MOEX
    token = _config.get("tinvest", {}).get("token", "")
    if not token:
        token = secrets.TINVEST_TOKEN

    if not token:
        logger.error("T-Invest token not configured")
        return {"error": "Token not configured", "selected_tickers": []}

    all_shares = get_all_moex_shares(
        token=token,
        sectors=None,  # Фильтрация по секторам позже, после обогащения
        only_tradable=True,
    )

    if not all_shares:
        logger.warning("No shares found from MOEX listing")
        return {"error": "No shares available", "selected_tickers": []}

    logger.info(f"MOEX listing: {len(all_shares)} tradable shares")

    # Применяем маппинг секторов по тикерам
    for share in all_shares:
        ticker = share.get("ticker", "")
        share["sector"] = TICKER_SECTORS.get(ticker, "other")

    # Фильтруем по секторам если указаны
    if sectors:
        sectors_lower = [s.lower() for s in sectors]
        all_shares = [s for s in all_shares if s.get("sector", "").lower() in sectors_lower]
        logger.info(f"After sector filter: {len(all_shares)} shares")

    # 2. Обогащаем данными (цены, объемы)
    candidates = _enrich_with_market_data(all_shares, limit=100)

    # 3. Фильтруем по минимальному объему
    if min_volume > 0:
        candidates = [c for c in candidates if c.get("avg_volume", 0) >= min_volume]

    # 4. Исключаем уже открытые позиции
    if open_positions:
        open_tickers = {p.get("ticker") for p in open_positions}
        candidates = [c for c in candidates if c["ticker"] not in open_tickers]

    # 5. Сортируем по score (если есть) или объему
    candidates.sort(key=lambda x: x.get("score", x.get("avg_volume", 0)), reverse=True)

    # 6. LLM или простая фильтрация
    if use_llm and _llm_client and _llm_client.is_available():
        result = _llm_select(candidates, max_picks, capital, open_positions or [])
        method = "llm"
    else:
        result = _filter_select(candidates, max_picks, sectors)
        method = "filter"

    # 7. Сохраняем результат
    scan_result = {
        "selected_tickers": result.get("selected_tickers", []),
        "all_candidates": candidates[:50],  # Топ-50 для дашборда
        "market_outlook": result.get("market_outlook", "neutral"),
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "total_scanned": len(all_shares),
        "filtered_count": len(candidates),
    }

    _store_scan_result(scan_result)

    return scan_result


def _ensure_client() -> bool:
    if _client is None:
        return False
    try:
        _client.ensure_connected()
        return True
    except Exception:
        return False


def _enrich_with_market_data(shares: list[dict], limit: int = 100) -> list[dict]:
    """Обогатить акции рыночными данными (цена, объем, волатильность)."""
    if not _ensure_client():
        return shares[:limit]

    enriched = []
    for share in shares[:limit]:
        ticker = share["ticker"]
        try:
            quote = _client.get_quote(ticker)
            price = quote.get("last", 0)
            if price <= 0:
                continue

            # Получаем исторические данные для расчета метрик
            candles = []
            try:
                candles = _client.get_historical_data(ticker, "1mo", "1d")
            except Exception:
                pass

            avg_volume = 0
            volatility = 0
            if candles:
                volumes = [c.get("volume", 0) for c in candles]
                avg_volume = sum(volumes) / len(volumes) if volumes else 0

                # Простая оценка волатильности
                closes = [float(c.get("close", 0)) for c in candles if c.get("close")]
                if len(closes) > 5:
                    returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
                    volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5 * (252 ** 0.5) * 100

            # Простой score на основе объема и волатильности
            score = 0
            if avg_volume > 1000000:
                score += 30
            elif avg_volume > 100000:
                score += 20
            elif avg_volume > 10000:
                score += 10

            if 15 <= volatility <= 60:
                score += 25
            elif volatility < 15:
                score += 10
            # Высокая волатильность — штраф
            if volatility > 80:
                score -= 10

            share_enriched = share.copy()
            share_enriched["price"] = price
            share_enriched["avg_volume"] = int(avg_volume)
            share_enriched["volatility"] = round(volatility, 2)
            share_enriched["score"] = score
            enriched.append(share_enriched)

        except Exception as e:
            logger.debug(f"Failed to enrich {ticker}: {e}")
            # Добавляем без обогащения
            share_copy = share.copy()
            share_copy["price"] = 0
            share_copy["avg_volume"] = 0
            share_copy["volatility"] = 0
            share_copy["score"] = 0
            enriched.append(share_copy)

    return enriched


def _llm_select(
    candidates: list[dict],
    max_picks: int,
    capital: float,
    open_positions: list[dict],
) -> dict:
    """Выбор тикеров через LLM."""
    # Формируем список акций для промпта
    stocks_list = ""
    for i, c in enumerate(candidates[:30]):  # Топ-30 для LLM
        price = c.get("price", 0)
        vol = c.get("avg_volume", 0)
        vwap = c.get("volatility", 0)
        sector = c.get("sector", "unknown")
        name = c.get("name", "")
        stocks_list += (
            f"{i+1}. {c['ticker']} ({name}) — Price: {price:.2f} RUB, "
            f"AvgVol: {vol:,}, Volatility: {vwap:.1f}%, Sector: {sector}\n"
        )

    open_tickers = ", ".join(p.get("ticker", "?") for p in open_positions) if open_positions else "None"
    allowed_sectors = ", ".join(SECTOR_DESCRIPTIONS.keys()) if _config else "all"

    prompt = SCAN_PROMPT.format(
        total_count=len(candidates),
        shown_count=min(30, len(candidates)),
        stocks_list=stocks_list,
        open_positions=open_tickers,
        capital=capital,
        allowed_sectors=allowed_sectors,
        max_picks=max_picks,
    )

    try:
        response = _llm_client.generate_json(prompt, system="You are a MOEX stock analyst. Respond only with valid JSON.")

        # Валидация ответа
        selected = response.get("selected_tickers", [])
        if not isinstance(selected, list):
            logger.warning("LLM returned non-list selected_tickers")
            selected = []

        # Ограничиваем max_picks
        selected = selected[:max_picks]

        # Валидация каждого тикера
        validated = []
        candidate_tickers = {c["ticker"] for c in candidates}
        for item in selected:
            ticker = item.get("ticker", "").upper()
            if ticker in candidate_tickers:
                validated.append({
                    "ticker": ticker,
                    "reason": item.get("reason", "LLM selected"),
                    "score": min(100, max(0, item.get("score", 50))),
                    "sector": item.get("sector", "unknown"),
                    "risk_level": item.get("risk_level", "medium"),
                })

        return {
            "selected_tickers": validated,
            "market_outlook": response.get("market_outlook", "neutral"),
            "reasoning": response.get("reasoning", ""),
        }

    except Exception as e:
        logger.error(f"LLM selection failed: {e}")
        # Fallback на простую фильтрацию
        return _filter_select(candidates, max_picks)


def _filter_select(
    candidates: list[dict],
    max_picks: int,
    sectors: list[str] = None,
) -> dict:
    """Простая фильтрация без LLM (fallback)."""
    # Группируем по секторам
    by_sector = {}
    for c in candidates:
        sector = c.get("sector", "other")
        if sector not in by_sector:
            by_sector[sector] = []
        by_sector[sector].append(c)

    selected = []
    # Берём по одному из каждого сектора (диверсификация)
    sector_order = sorted(by_sector.keys(), key=lambda s: len(by_sector[s]), reverse=True)

    for sector in sector_order:
        if len(selected) >= max_picks:
            break
        # Лучший в секторе
        best = max(by_sector[sector], key=lambda x: x.get("score", 0))
        if best.get("score", 0) > 0:
            selected.append({
                "ticker": best["ticker"],
                "reason": f"Top in {sector} sector (score: {best.get('score', 0)})",
                "score": best.get("score", 50),
                "sector": sector,
                "risk_level": "medium",
            })

    # Если не набрали — добавляем просто лучшие по score
    if len(selected) < max_picks:
        remaining = [c for c in candidates if c["ticker"] not in {s["ticker"] for s in selected}]
        remaining.sort(key=lambda x: x.get("score", 0), reverse=True)
        for c in remaining[:max_picks - len(selected)]:
            if c.get("score", 0) > 0:
                selected.append({
                    "ticker": c["ticker"],
                    "reason": f"Highest score: {c.get('score', 0)}",
                    "score": c.get("score", 50),
                    "sector": c.get("sector", "unknown"),
                    "risk_level": "medium",
                })

    return {
        "selected_tickers": selected[:max_picks],
        "market_outlook": "neutral",
    }


def _store_scan_result(result: dict):
    """Сохранить результат сканирования в БД."""
    try:
        from tools.memory import get_db_path
        conn = sqlite3.connect(get_db_path(), timeout=5)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO scan_results
            (scan_time, method, total_scanned, filtered_count, selected_count,
             market_outlook, selected_tickers, all_candidates)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.get("scan_time"),
            result.get("method", "unknown"),
            result.get("total_scanned", 0),
            result.get("filtered_count", 0),
            len(result.get("selected_tickers", [])),
            result.get("market_outlook", "neutral"),
            json.dumps(result.get("selected_tickers", [])),
            json.dumps(result.get("all_candidates", [])[:20]),  # Только топ-20
        ))

        conn.commit()
        conn.close()
        logger.info(f"Scan result stored: {len(result.get('selected_tickers', []))} tickers selected")

    except Exception as e:
        logger.error(f"Failed to store scan result: {e}")


def get_scan_history(limit: int = 10) -> list[dict]:
    """Получить историю сканирований."""
    try:
        from tools.memory import get_db_path
        conn = sqlite3.connect(get_db_path(), timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM scan_results ORDER BY scan_time DESC LIMIT ?
        """, (limit,))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Парсим JSON
        for row in rows:
            try:
                row["selected_tickers"] = json.loads(row.get("selected_tickers", "[]"))
            except Exception:
                row["selected_tickers"] = []
            try:
                row["all_candidates"] = json.loads(row.get("all_candidates", "[]"))
            except Exception:
                row["all_candidates"] = []

        return rows

    except Exception as e:
        logger.error(f"Failed to get scan history: {e}")
        return []


def get_latest_scan() -> Optional[dict]:
    """Получить последнее сканирование."""
    history = get_scan_history(limit=1)
    return history[0] if history else None
