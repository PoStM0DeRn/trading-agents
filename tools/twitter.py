"""Инструменты для парсинга X.com через Nitter."""

import logging
import time

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.catsarch.com",
    "https://nitter.tiekoetter.com",
    "https://nitter.poast.org",
    "https://nitter.kareem.one",
    "https://nitter.privacyredirect.com",
    "https://nitter.space",
    "https://lightbrd.com",
]

_twitter_cache: dict = {}
_twitter_cache_ttl = 900


def search_twitter(query: str, limit: int = 10) -> list[dict]:
    """Поиск твитов по запросу через Nitter (HTML + RSS)."""
    cache_key = f"search_{query}_{limit}"
    if cache_key in _twitter_cache:
        cached_time, cached_data = _twitter_cache[cache_key]
        if time.time() - cached_time < _twitter_cache_ttl:
            logger.info(f"[Twitter] Cache hit for '{query}'")
            return cached_data

    tweets = []
    for instance in NITTER_INSTANCES:
        try:
            url = f"{instance}/search"
            response = httpx.get(
                url,
                params={"q": query, "f": "tweets"},
                timeout=8.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            if response.status_code == 200:
                tweets = _parse_nitter_timeline(response.text, limit)
                if tweets:
                    logger.info(f"[Twitter] {instance} -> {len(tweets)} tweets for '{query}'")
                    break
            else:
                logger.debug(f"[Twitter] {instance} returned status {response.status_code}")
        except Exception as e:
            logger.debug(f"[Twitter] {instance} HTML failed: {e}")
            continue

    if not tweets:
        for instance in NITTER_INSTANCES:
            try:
                rss_url = f"{instance}/search/rss"
                response = httpx.get(
                    rss_url,
                    params={"q": query, "f": "tweets"},
                    timeout=8.0,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                if response.status_code == 200 and "xml" in response.headers.get("content-type", ""):
                    tweets = _parse_nitter_rss(response.text, limit)
                    if tweets:
                        logger.info(f"[Twitter] {instance} RSS -> {len(tweets)} tweets for '{query}'")
                        break
            except Exception as e:
                logger.debug(f"[Twitter] {instance} RSS failed: {e}")
                continue

    if not tweets:
        logger.warning(f"[Twitter] No tweets found for '{query}' from any Nitter instance")

    _twitter_cache[cache_key] = (time.time(), tweets)
    return tweets


def get_user_tweets(username: str, limit: int = 10) -> list[dict]:
    """Получить твиты конкретного пользователя."""
    username = username.lstrip("@")
    cache_key = f"user_{username}_{limit}"
    if cache_key in _twitter_cache:
        cached_time, cached_data = _twitter_cache[cache_key]
        if time.time() - cached_time < _twitter_cache_ttl:
            return cached_data

    tweets = []
    for instance in NITTER_INSTANCES:
        try:
            url = f"{instance}/{username}"
            response = httpx.get(
                url,
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            if response.status_code == 200:
                tweets = _parse_nitter_timeline(response.text, limit)
                if tweets:
                    logger.info(f"[Twitter] {instance} -> {len(tweets)} tweets from @{username}")
                    break
        except Exception as e:
            logger.debug(f"[Twitter] {instance} failed for @{username}: {e}")
            continue

    _twitter_cache[cache_key] = (time.time(), tweets)
    return tweets


def get_hashtag_tweets(hashtag: str, limit: int = 10) -> list[dict]:
    """Получить твиты по хэштегу."""
    query = hashtag if hashtag.startswith("#") else f"#{hashtag}"
    return search_twitter(query, limit)


def _parse_nitter_timeline(html: str, limit: int) -> list[dict]:
    """Парсинг HTML таймлайна Nitter."""
    soup = BeautifulSoup(html, "html.parser")
    tweets = []

    for item in soup.find_all("div", class_="timeline-item")[:limit]:
        try:
            content_div = item.find("div", class_="tweet-content")
            if not content_div:
                continue

            text = content_div.get_text(strip=True)
            if not text:
                continue

            author_link = item.find("a", class_="username")
            author = author_link.text.lstrip("@") if author_link else ""

            date_span = item.find("span", class_="tweet-date")
            date_str = ""
            tweet_link = ""
            if date_span:
                date_a = date_span.find("a")
                if date_a:
                    date_str = date_a.get("title", "")
                    href = date_a.get("href", "")
                    tweet_link = href

            likes = 0
            retweets = 0
            try:
                stats_container = item.find("div", class_="tweet-stat")
                if stats_container:
                    stat_spans = stats_container.find_all("span", class_="tweet-stat")
                    for stat in stat_spans:
                        icon = stat.find("span", class_="icon-heart")
                        if icon:
                            num_text = stat.get_text(strip=True).replace(",", "")
                            if num_text.isdigit():
                                likes = int(num_text)
                        icon_rt = stat.find("span", class_="icon-retweet")
                        if icon_rt:
                            num_text = stat.get_text(strip=True).replace(",", "")
                            if num_text.isdigit():
                                retweets = int(num_text)
            except Exception:
                pass

            full_url = ""
            if tweet_link:
                username_part = f"/{author}" if author else ""
                full_url = f"https://x.com{username_part}{tweet_link}"

            tweets.append({
                "text": text,
                "author": author,
                "date": date_str,
                "url": full_url,
                "likes": likes,
                "retweets": retweets,
                "source": "X.com",
            })
        except Exception as e:
            logger.debug(f"[Twitter] Failed to parse tweet: {e}")
            continue

    return tweets[:limit]


def _parse_nitter_rss(xml_content: str, limit: int) -> list[dict]:
    """Парсинг RSS ленты Nitter."""
    soup = BeautifulSoup(xml_content, "xml")
    tweets = []

    for item in soup.find_all("item")[:limit]:
        try:
            title = item.find("title")
            description = item.find("description")
            link = item.find("link")
            pub_date = item.find("pubDate")
            creator = item.find("dc:creator")

            text = ""
            if description:
                desc_soup = BeautifulSoup(description.text, "html.parser")
                text = desc_soup.get_text(strip=True)
            elif title:
                text = title.get_text(strip=True)

            if not text:
                continue

            author = creator.text.lstrip("@") if creator else ""
            date_str = pub_date.text if pub_date else ""
            url = link.text if link else ""

            tweets.append({
                "text": text,
                "author": author,
                "date": date_str,
                "url": url,
                "likes": 0,
                "retweets": 0,
                "source": "X.com",
            })
        except Exception as e:
            logger.debug(f"[Twitter] Failed to parse RSS item: {e}")
            continue

    return tweets[:limit]


def get_twitter_snapshot(ticker: str, company: str) -> dict:
    """Полный снимок по тикеру из X.com."""
    queries = [f"${ticker}", company]
    all_tweets = []

    for query in queries:
        tweets = search_twitter(query, limit=5)
        all_tweets.extend(tweets)

    unique = []
    seen = set()
    for t in all_tweets:
        key = t["text"][:100]
        if key not in seen:
            unique.append(t)
            seen.add(key)

    return {
        "ticker": ticker,
        "tweets": unique[:10],
        "count": len(unique),
    }
