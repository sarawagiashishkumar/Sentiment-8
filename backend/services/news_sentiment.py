"""
News & Fallback Sentiment Engine — Section 4 of Master Spec.

Fetches headlines from free RSS feeds (MoneyControl, Economic Times),
runs VADER sentiment scoring in pure Python, and computes aggregated
NewsFlag per symbol/sector.

All calculations are pure Python. NO LLM numeric work.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Lazy imports to avoid startup failures
_vader_analyzer = None
_feedparser = None


def _get_vader():
    global _vader_analyzer
    if _vader_analyzer is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader_analyzer = SentimentIntensityAnalyzer()
        except ImportError:
            logger.warning("vaderSentiment not installed; sentiment scoring disabled")
    return _vader_analyzer


def _get_feedparser():
    global _feedparser
    if _feedparser is None:
        try:
            import feedparser as fp
            _feedparser = fp
        except ImportError:
            logger.warning("feedparser not installed; RSS fetching disabled")
    return _feedparser


# ---------------------------------------------------------------------------
# RSS Feed Configuration
# ---------------------------------------------------------------------------

NewsFlag = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]

# Free financial news RSS feeds for Indian markets
RSS_FEEDS: list[dict[str, str]] = [
    {"name": "MoneyControl", "url": "https://www.moneycontrol.com/rss/MCtopnews.xml"},
    {"name": "MoneyControl_Markets", "url": "https://www.moneycontrol.com/rss/marketreports.xml"},
    {"name": "ET_Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"name": "ET_Stocks", "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"},
    {"name": "LiveMint", "url": "https://www.livemint.com/rss/markets"},
]

# Configurable thresholds
SENTIMENT_POSITIVE_THRESHOLD = 0.15
SENTIMENT_NEGATIVE_THRESHOLD = -0.15
MIN_NEWS_COUNT_FOR_FLAG = 2
NEWS_LOOKBACK_HOURS = 12

# In-memory cache for news items
_news_cache: dict[str, list[dict]] = {}
_news_cache_ts: float = 0.0
NEWS_CACHE_TTL_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# 4.1  News Fetching
# ---------------------------------------------------------------------------

def _fetch_rss_headlines(max_per_feed: int = 30) -> list[dict[str, Any]]:
    """
    Fetch headlines from all configured RSS feeds.
    Returns list of {title, summary, published, source, link}.
    """
    fp = _get_feedparser()
    if fp is None:
        return []

    all_items: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for feed_cfg in RSS_FEEDS:
        try:
            feed = fp.parse(feed_cfg["url"])
            for entry in feed.entries[:max_per_feed]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        published = now

                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                # Clean HTML tags from summary
                summary = re.sub(r"<[^>]+>", "", summary).strip()

                all_items.append({
                    "title": title,
                    "summary": summary[:300],
                    "published": published or now,
                    "source": feed_cfg["name"],
                    "link": getattr(entry, "link", ""),
                })
        except Exception as e:
            logger.warning(f"RSS fetch failed for {feed_cfg['name']}: {e}")

    return all_items


def _score_headline(title: str, summary: str = "") -> float:
    """
    Score a single headline using VADER sentiment.
    Returns compound score in [-1.0, +1.0].
    """
    analyzer = _get_vader()
    if analyzer is None:
        return 0.0

    text = f"{title}. {summary}" if summary else title
    scores = analyzer.polarity_scores(text)
    return scores.get("compound", 0.0)


def _match_symbol_in_text(text: str, symbol: str) -> bool:
    """Check if a symbol name appears in headline/summary text."""
    text_upper = text.upper()
    # Direct symbol match
    if symbol.upper() in text_upper:
        return True
    # Common aliases
    aliases: dict[str, list[str]] = {
        "NIFTY": ["NIFTY", "NIFTY50", "NIFTY 50"],
        "BANKNIFTY": ["BANKNIFTY", "BANK NIFTY", "NIFTY BANK"],
        "RELIANCE": ["RELIANCE", "RIL", "RELIANCE INDUSTRIES"],
        "TCS": ["TCS", "TATA CONSULTANCY"],
        "HDFCBANK": ["HDFC BANK", "HDFCBANK"],
        "ICICIBANK": ["ICICI BANK", "ICICIBANK"],
        "INFY": ["INFOSYS", "INFY"],
        "SBIN": ["SBI", "STATE BANK"],
        "AXISBANK": ["AXIS BANK", "AXISBANK"],
        "KOTAKBANK": ["KOTAK", "KOTAKBANK", "KOTAK MAHINDRA"],
        "TATAMOTORS": ["TATA MOTORS", "TATAMOTORS"],
        "ITC": ["ITC LIMITED", "ITC"],
        "LT": ["LARSEN", "L&T", "LARSEN AND TOUBRO"],
        "BAJFINANCE": ["BAJAJ FINANCE", "BAJFINANCE"],
        "MARUTI": ["MARUTI", "MARUTI SUZUKI"],
    }
    for alias in aliases.get(symbol.upper(), []):
        if alias in text_upper:
            return True
    return False


# Sector keyword mapping for sector-level sentiment
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Banking": ["BANK", "BANKING", "RBI", "INTEREST RATE", "CREDIT", "NPA", "LOAN"],
    "IT": ["IT SECTOR", "TECH", "SOFTWARE", "DIGITAL", "SAAS", "AI"],
    "Pharma": ["PHARMA", "DRUG", "HEALTHCARE", "FDA", "MEDICINE"],
    "Auto": ["AUTO", "AUTOMOBILE", "EV", "ELECTRIC VEHICLE", "CAR"],
    "Energy": ["OIL", "GAS", "ENERGY", "POWER", "PETROLEUM", "CRUDE"],
    "Metal": ["METAL", "STEEL", "ALUMINIUM", "MINING", "COPPER"],
    "FMCG": ["FMCG", "CONSUMER", "FOOD", "BEVERAGE"],
    "Realty": ["REAL ESTATE", "REALTY", "PROPERTY", "HOUSING"],
    "Infrastructure": ["INFRA", "INFRASTRUCTURE", "CONSTRUCTION", "ROAD"],
}


def _match_sector_in_text(text: str, sector: str) -> bool:
    """Check if sector keywords appear in text."""
    text_upper = text.upper()
    keywords = SECTOR_KEYWORDS.get(sector, [sector.upper()])
    return any(kw in text_upper for kw in keywords)


# ---------------------------------------------------------------------------
# 4.2  Aggregated Symbol/Sector Sentiment
# ---------------------------------------------------------------------------

def refresh_news_cache() -> int:
    """
    Refresh the news headline cache from RSS feeds.
    Returns number of items fetched.
    """
    global _news_cache, _news_cache_ts

    now = time.time()
    if now - _news_cache_ts < NEWS_CACHE_TTL_SECONDS and _news_cache:
        return sum(len(v) for v in _news_cache.values())

    items = _fetch_rss_headlines()
    if not items:
        return 0

    # Score each headline
    scored: list[dict] = []
    for item in items:
        sentiment = _score_headline(item["title"], item.get("summary", ""))
        item["sentiment_score"] = round(sentiment, 3)
        scored.append(item)

    _news_cache = {"all": scored}
    _news_cache_ts = now
    logger.info(f"News cache refreshed: {len(scored)} headlines scored")
    return len(scored)


def get_symbol_sentiment(
    symbol: str,
    lookback_hours: int = NEWS_LOOKBACK_HOURS,
) -> dict[str, Any]:
    """
    Get aggregated sentiment for a specific symbol.

    Returns:
      - news_count: int
      - avg_sentiment: float (-1 to +1)
      - news_flag: NewsFlag (POSITIVE/NEGATIVE/NEUTRAL)
      - headlines: list of relevant headlines (top 5)
    """
    # Ensure cache is fresh
    if not _news_cache or (time.time() - _news_cache_ts) > NEWS_CACHE_TTL_SECONDS:
        refresh_news_cache()

    all_items = _news_cache.get("all", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    relevant: list[dict] = []
    for item in all_items:
        pub = item.get("published")
        if pub and pub < cutoff:
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        if _match_symbol_in_text(text, symbol):
            relevant.append(item)

    if not relevant:
        return {
            "symbol": symbol,
            "news_count": 0,
            "avg_sentiment": 0.0,
            "news_flag": "NEUTRAL",
            "headlines": [],
        }

    scores = [item.get("sentiment_score", 0.0) for item in relevant]
    avg_sent = sum(scores) / len(scores) if scores else 0.0

    # Determine NewsFlag
    if avg_sent > SENTIMENT_POSITIVE_THRESHOLD and len(relevant) >= MIN_NEWS_COUNT_FOR_FLAG:
        flag: NewsFlag = "POSITIVE"
    elif avg_sent < SENTIMENT_NEGATIVE_THRESHOLD and len(relevant) >= MIN_NEWS_COUNT_FOR_FLAG:
        flag = "NEGATIVE"
    else:
        flag = "NEUTRAL"

    # Top 5 headlines by absolute sentiment
    top = sorted(relevant, key=lambda x: abs(x.get("sentiment_score", 0)), reverse=True)[:5]

    return {
        "symbol": symbol,
        "news_count": len(relevant),
        "avg_sentiment": round(avg_sent, 3),
        "news_flag": flag,
        "headlines": [
            {
                "title": h["title"],
                "source": h["source"],
                "sentiment": h.get("sentiment_score", 0.0),
            }
            for h in top
        ],
    }


def get_sector_sentiment(
    sector: str,
    lookback_hours: int = NEWS_LOOKBACK_HOURS,
) -> dict[str, Any]:
    """
    Get aggregated sentiment for a sector.
    """
    if not _news_cache or (time.time() - _news_cache_ts) > NEWS_CACHE_TTL_SECONDS:
        refresh_news_cache()

    all_items = _news_cache.get("all", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    relevant: list[dict] = []
    for item in all_items:
        pub = item.get("published")
        if pub and pub < cutoff:
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        if _match_sector_in_text(text, sector):
            relevant.append(item)

    if not relevant:
        return {
            "sector": sector,
            "news_count": 0,
            "avg_sentiment": 0.0,
            "news_flag": "NEUTRAL",
        }

    scores = [item.get("sentiment_score", 0.0) for item in relevant]
    avg_sent = sum(scores) / len(scores) if scores else 0.0

    if avg_sent > SENTIMENT_POSITIVE_THRESHOLD and len(relevant) >= MIN_NEWS_COUNT_FOR_FLAG:
        flag: NewsFlag = "POSITIVE"
    elif avg_sent < SENTIMENT_NEGATIVE_THRESHOLD and len(relevant) >= MIN_NEWS_COUNT_FOR_FLAG:
        flag = "NEGATIVE"
    else:
        flag = "NEUTRAL"

    return {
        "sector": sector,
        "news_count": len(relevant),
        "avg_sentiment": round(avg_sent, 3),
        "news_flag": flag,
    }


def get_market_sentiment_summary() -> dict[str, Any]:
    """
    Get overall market sentiment from all cached headlines.
    """
    if not _news_cache or (time.time() - _news_cache_ts) > NEWS_CACHE_TTL_SECONDS:
        refresh_news_cache()

    all_items = _news_cache.get("all", [])
    if not all_items:
        return {
            "total_headlines": 0,
            "avg_sentiment": 0.0,
            "market_flag": "NEUTRAL",
            "positive_pct": 0.0,
            "negative_pct": 0.0,
        }

    scores = [item.get("sentiment_score", 0.0) for item in all_items]
    avg = sum(scores) / len(scores)
    positive = sum(1 for s in scores if s > 0.05) / len(scores) * 100
    negative = sum(1 for s in scores if s < -0.05) / len(scores) * 100

    if avg > 0.10:
        market_flag: NewsFlag = "POSITIVE"
    elif avg < -0.10:
        market_flag = "NEGATIVE"
    else:
        market_flag = "NEUTRAL"

    return {
        "total_headlines": len(all_items),
        "avg_sentiment": round(avg, 3),
        "market_flag": market_flag,
        "positive_pct": round(positive, 1),
        "negative_pct": round(negative, 1),
    }
