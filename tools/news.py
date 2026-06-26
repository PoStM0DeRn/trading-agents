"""Инструменты для работы с новостями и анализом текста."""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from tools.retry import retry

logger = logging.getLogger(__name__)

_llm_client = None

TICKER_NAMES = {
    "SBER": "Сбербанк", "GAZP": "Газпром", "LKOH": "Лукойл",
    "GMKN": "Норникель", "YDEX": "Яндекс", "VTBR": "ВТБ",
    "ROSN": "Роснефть", "NVTK": "НОВАТЭК", "SNGS": "Сургутнефтегаз",
    "TATN": "Татнефть", "ALRS": "АЛРОСА", "PLZL": "Полюс",
    "PHOR": "ФосАгро", "AFLT": "Аэрофлот",
}

_news_cache: dict = {}
_news_cache_ttl = 900
_DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# ── Source configs ─────────────────────────────────────────────────
NEWS_SOURCES = {
    "interfax": {
        "name": "Interfax", "type": "html",
        "url": "https://www.interfax.ru/search/?query={query}",
        "parser": "html.parser",
        "item_selector": ("div", "story"),
        "title_selector": ("a", "story__title"),
        "desc_selector": ("p", "story__intro"),
        "date_selector": ("span", "story__date"),
        "url_base": "https://www.interfax.ru",
    },
    "rbc": {
        "name": "RBC", "type": "html",
        "url": "https://www.rbc.ru/search/?query={query}&type=news&dateFrom=&dateTo=",
        "parser": "html.parser",
        "item_selector": ("div", "search-item"),
        "title_selector": ("a", "search-item__link"),
        "desc_selector": ("p", "search-item__text"),
        "date_selector": ("span", "search-item__category"),
    },
    "bing_ru": {
        "name": "Bing News", "type": "rss",
        "url": "https://www.bing.com/news/search",
        "params": {"format": "rss", "cc": "ru", "setlang": "ru"},
        "query_param": "q", "query_template": "{company} акции новости",
    },
    "bing_en": {
        "name": "Bing News", "type": "rss",
        "url": "https://www.bing.com/news/search",
        "params": {"format": "rss"},
        "query_param": "q", "query_template": "{ticker} stock",
    },
    "marketwatch": {
        "name": "MarketWatch", "type": "rss",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    },
    "google_ru": {
        "name": "Google News", "type": "rss",
        "url": "https://news.google.com/rss/search",
        "params": {"hl": "ru", "gl": "RU", "ceid": "RU:ru"},
        "query_param": "q", "query_template": "{company} акции MOEX",
        "source_tag": True,
    },
    "tass": {
        "name": "TASS", "type": "rss",
        "urls": ["https://tass.ru/rss/v2.xml"],
        "keyword_filter": True,
        "keywords_template": ["{company}", "{ticker}", "акци", "дивиденд", "мосбюрж", "moex", "бирж", "финанс"],
    },
    "kommersant": {
        "name": "Коммерсантъ", "type": "rss",
        "urls": ["https://www.kommersant.ru/RSS/news.xml"],
        "title_filter": True,
    },
    "vedomosti": {
        "name": "Ведомости", "type": "rss",
        "urls": ["https://www.vedomosti.ru/rss/news.xml", "https://www.vedomosti.ru/rss/issue.xml"],
        "title_filter": True,
    },
    "finam": {
        "name": "Финам", "type": "html_links",
        "url": "https://www.finam.ru/analysis/conews/",
        "min_text_len": 20,
    },
    "ria": {
        "name": "РИА Новости", "type": "rss",
        "urls": ["https://ria.ru/export/rss2/archive/index.xml"],
        "title_filter": True,
    },
}


def set_llm_client(client):
    global _llm_client
    _llm_client = client


def _get_company_name(ticker: str) -> str:
    return TICKER_NAMES.get(ticker.upper(), ticker)


# ── Generic fetcher ────────────────────────────────────────────────

@retry(max_retries=2, base_delay=1.0, exceptions=(httpx.HTTPError,))
def _fetch_source(cfg: dict, query: str, ticker: str, limit: int) -> list[dict]:
    source_name = cfg["name"]
    src_type = cfg["type"]
    company = _get_company_name(ticker)
    urls = cfg.get("urls") or [cfg.get("url", "")]
    all_articles = []

    for url_template in urls:
        try:
            url = url_template.format(query=query) if "{query}" in url_template else url_template
            params = dict(cfg.get("params", {}))
            if cfg.get("query_param") and cfg.get("query_template"):
                params[cfg["query_param"]] = cfg["query_template"].format(
                    company=company, ticker=ticker, query=query
                )
            response = httpx.get(
                url, params=params or None, timeout=10.0,
                follow_redirects=True, headers={"User-Agent": _DEFAULT_UA},
            )
            if response.status_code != 200:
                continue
            if src_type == "rss":
                articles = _parse_rss(response, cfg, ticker, company, query, limit)
            elif src_type == "html":
                articles = _parse_html(response, cfg, ticker, limit)
            elif src_type == "html_links":
                articles = _parse_html_links(response, cfg, ticker, query, limit)
            else:
                continue
            all_articles.extend(articles)
            if all_articles:
                break
        except Exception as e:
            logger.warning(f"{source_name} failed: {e}")
    return all_articles[:limit]


def _parse_rss(response, cfg: dict, ticker: str, company: str, query: str, limit: int) -> list[dict]:
    soup = BeautifulSoup(response.content, "xml")
    source_name = cfg["name"]
    articles = []
    query_lower = query.lower()

    for item in soup.find_all("item"):
        title = item.find("title")
        if not title:
            continue
        headline = title.text.strip()
        if cfg.get("title_filter") and query_lower not in headline.lower():
            continue
        if cfg.get("keyword_filter"):
            keywords = [kw.format(company=company.lower(), ticker=ticker.lower())
                        for kw in cfg.get("keywords_template", [])]
            desc = item.find("description")
            desc_lower = (desc.text if desc else "").lower()
            if not any(kw in headline.lower() or kw in desc_lower for kw in keywords):
                continue
        desc = item.find("description")
        link = item.find("link")
        pub_date = item.find("pubDate")
        source_tag = item.find("source") if cfg.get("source_tag") else None
        articles.append({
            "headline": headline,
            "summary": desc.text.strip()[:500] if desc else "",
            "url": link.text.strip() if link else "",
            "source": source_tag.text.strip() if source_tag else source_name,
            "date": pub_date.text if pub_date else "",
            "ticker": ticker,
        })
        if len(articles) >= limit:
            break
    return articles


def _parse_html(response, cfg: dict, ticker: str, limit: int) -> list[dict]:
    soup = BeautifulSoup(response.text, cfg.get("parser", "html.parser"))
    source_name = cfg["name"]
    item_tag, item_class = cfg["item_selector"]
    title_tag, title_class = cfg["title_selector"]
    desc_sel = cfg.get("desc_selector")
    date_sel = cfg.get("date_selector")
    url_base = cfg.get("url_base", "")
    articles = []
    for item in soup.find_all(item_tag, class_=item_class)[:limit]:
        title_el = item.find(title_tag, class_=title_class)
        if not title_el:
            continue
        href = title_el.get("href", "")
        if url_base and href and not href.startswith("http"):
            href = f"{url_base}{href}"
        desc_el = item.find(desc_sel[0], class_=desc_sel[1]) if desc_sel else None
        date_el = item.find(date_sel[0], class_=date_sel[1]) if date_sel else None
        articles.append({
            "headline": title_el.get_text(strip=True),
            "summary": desc_el.get_text(strip=True)[:500] if desc_el else "",
            "url": href, "source": source_name,
            "date": date_el.get_text(strip=True) if date_el else "",
            "ticker": ticker,
        })
    return articles


def _parse_html_links(response, cfg: dict, ticker: str, query: str, limit: int) -> list[dict]:
    soup = BeautifulSoup(response.text, "html.parser")
    source_name = cfg["name"]
    url_base = cfg.get("url_base", "")
    min_len = cfg.get("min_text_len", 20)
    query_lower = query.lower()
    articles = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if query_lower in text.lower() and len(text) > min_len:
            href = a["href"]
            if url_base and not href.startswith("http"):
                href = f"{url_base}{href}"
            articles.append({
                "headline": text[:200], "summary": text[:500],
                "url": href, "source": source_name, "date": "", "ticker": ticker,
            })
            if len(articles) >= limit:
                break
    return articles


# ── Dedup & relevance ──────────────────────────────────────────────

def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    if not articles:
        return []
    unique = [articles[0]]
    for art in articles[1:]:
        headline = art.get("headline", "").lower().strip()
        is_dup = False
        for existing in unique:
            ex = existing.get("headline", "").lower().strip()
            if headline == ex or headline in ex or ex in headline:
                is_dup = True
                break
            h_words, e_words = set(headline.split()), set(ex.split())
            if h_words and e_words and len(h_words & e_words) / min(len(h_words), len(e_words)) > 0.7:
                is_dup = True
                break
        if not is_dup:
            unique.append(art)
    return unique


_FINANCIAL_KEYWORDS = [
    "акци", "дивиденд", "прибыл", "убытк", "капитал", "рынок", "бирж",
    "торгов", "цена", "рост", "снижени", "аналитик", "прогноз",
    "stock", "share", "dividend", "profit", "loss", "market", "trading",
    "quote", "price", "growth", "decline", "analyst", "forecast",
    "MOEX", "RTS", "SBER", "GAZP", "LKOH", "GMKN", "YDEX", "VTBR", "ROSN", "NVTK",
    "Сбер", "Газпром", "Лукойл", "ГМКНорникель", "Яндекс", "ВТБ", "Роснефть", "Новатэк",
]


def _filter_relevant(articles: list[dict], ticker: str, company: str) -> list[dict]:
    if not articles:
        return []
    tl, cl = ticker.lower(), company.lower()
    relevant = []
    for art in articles:
        text = (art.get("headline", "") + " " + art.get("summary", "")).lower()
        has_ticker = tl in text
        has_company = cl in text
        has_financial = any(kw.lower() in text for kw in _FINANCIAL_KEYWORDS)
        if (has_ticker or has_company) and has_financial:
            relevant.append(art)
        elif has_ticker or has_company:
            relevant.append(art)
        elif has_financial and sum(1 for kw in _FINANCIAL_KEYWORDS if kw.lower() in text) >= 3:
            relevant.append(art)
    return relevant if relevant else articles[:3]


# ── Public API ─────────────────────────────────────────────────────

def search_news(ticker: str, date_from: str = None, date_to: str = None, limit: int = 15) -> list[dict]:
    import time
    import concurrent.futures
    cache_key = f"{ticker}_{limit}"
    if cache_key in _news_cache:
        cached_time, cached_articles = _news_cache[cache_key]
        if time.time() - cached_time < _news_cache_ttl:
            logger.info(f"[News] Cache hit for {ticker} ({len(cached_articles)} articles)")
            return cached_articles

    company = _get_company_name(ticker)
    query = company
    all_articles = []

    sources = [
        ("Google News RU", lambda: _fetch_source(NEWS_SOURCES["google_ru"], query, ticker, limit)),
        ("TASS", lambda: _fetch_source(NEWS_SOURCES["tass"], query, ticker, limit)),
        ("Interfax", lambda: _fetch_source(NEWS_SOURCES["interfax"], query, ticker, limit)),
        ("RBC", lambda: _fetch_source(NEWS_SOURCES["rbc"], query, ticker, limit)),
        ("Bing News RU", lambda: _fetch_source(NEWS_SOURCES["bing_ru"], query, ticker, limit)),
        ("Коммерсантъ", lambda: _fetch_source(NEWS_SOURCES["kommersant"], query, ticker, limit)),
        ("Ведомости", lambda: _fetch_source(NEWS_SOURCES["vedomosti"], query, ticker, limit)),
        ("РИА Новости", lambda: _fetch_source(NEWS_SOURCES["ria"], query, ticker, limit)),
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_source = {executor.submit(fn): name for name, fn in sources}
        for future in concurrent.futures.as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                result = future.result()
                if result:
                    all_articles.extend(result)
                    logger.info(f"[News] {source_name} → {len(result)} articles for {ticker}")
            except Exception as e:
                logger.warning(f"[News] {source_name} failed for {ticker}: {e}")

    if not all_articles:
        logger.warning(f"[News] No articles found for {ticker} from any source")
        return []

    unique = _deduplicate_articles(all_articles)
    logger.info(f"[News] Aggregated {len(all_articles)} total → {len(unique)} unique for {ticker}")
    filtered = _filter_relevant(unique, ticker, company)
    logger.info(f"[News] After relevance filter: {len(filtered)} articles for {ticker}")

    result = filtered[:limit]
    _news_cache[cache_key] = (time.time(), result)
    return result


@retry(max_retries=2, base_delay=1.0, exceptions=(httpx.HTTPError,))
def fetch_article(url: str) -> str:
    try:
        response = httpx.get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        return article.get_text(strip=True, separator="\n")[:5000] if article else soup.get_text(strip=True, separator="\n")[:5000]
    except Exception as e:
        logger.error(f"Failed to fetch article {url}: {e}")
        return ""


def get_news_sentiment(ticker: str, date_range: str = "7d") -> dict:
    articles = search_news(ticker, limit=5)
    if not articles:
        return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "articles_count": 0}
    texts = [f"- {a['headline']}: {a['summary'][:200]}" for a in articles]
    combined = "\n".join(texts)
    if _llm_client:
        company = _get_company_name(ticker)
        prompt = f"""Проанализируй тональность новостей о компании {company} ({ticker}):\n\n{combined}\n\nВерни JSON: {{"positive": 0.7, "negative": 0.1, "neutral": 0.2}}"""
        try:
            result = _llm_client.generate_json(prompt)
            result["articles_count"] = len(articles)
            return result
        except Exception as e:
            logger.warning(f"LLM sentiment failed: {e}")
    return _simple_sentiment_ru(combined)


def detect_entities(text: str) -> list[dict]:
    if _llm_client:
        prompt = f"""Извлеки сущности. Верни JSON: [{{"text": "...", "type": "COMPANY|PERSON|EVENT", "relevance": 0.0-1.0}}]\n\nТекст: {text[:2000]}"""
        try:
            return _llm_client.generate_json(prompt, system="Извлеки сущности. Только JSON.")
        except Exception:
            pass
    return [{"text": t, "type": "TICKER", "relevance": 0.5} for t in set(re.findall(r"\b([A-Z]{2,5})\b", text))]


def classify_impact(event_description: str) -> float:
    if _llm_client:
        prompt = f"""Оцени влияние от 0 до 1:\n\n{event_description[:1000]}\n\nВерни JSON: {{"impact_score": <float>}}"""
        try:
            return float(_llm_client.generate_json(prompt).get("impact_score", 0.5))
        except Exception:
            pass
    high_impact = ["дивиденд", "слияние", "поглощение", "отчётность", "банкротство", "штраф", "суд", "рекорд", "падение", "рост"]
    score = 0.3 + sum(0.1 for w in high_impact if w in event_description.lower())
    return min(score, 1.0)


def _simple_sentiment_ru(text: str) -> dict:
    pos = ["прибыль", "рост", "поступление", "рекорд", "усиление", "повышение", "покупать", "рекомендация", "хороший", "сильный", "положительный", "бычий", "восхождение", "подъём", "успех", "прорыв", "дивиденд", "прирост", "оптимизм"]
    neg = ["убыток", "падение", "снижение", "проблемы", "штраф", "суд", "продавать", "плохой", "слабый", "отрицательный", "медвежий", "обвал", "крах", "провал", "проигрыш", "риск", "кража", "санкция", "война"]
    tl = text.lower()
    p, n = sum(1 for w in pos if w in tl), sum(1 for w in neg if w in tl)
    t = p + n + 1
    return {"positive": round(p / t, 2), "negative": round(n / t, 2), "neutral": round(1 - (p + n) / t, 2), "articles_count": 0}
