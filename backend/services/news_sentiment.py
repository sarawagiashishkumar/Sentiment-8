"""
News & Fallback Sentiment Engine — Section 4 of Master Spec.

Batch 4 enhancements:
- 4.1: NEWS_FETCH with parallel verification (cross-source dedup)
- 4.2: NEWS_AGGREGATE with recency weighting and windowed avg
- 4.3: CONTINUOUS_MONITOR background task (market hours only)

Fetches headlines from free RSS feeds (MoneyControl, Economic Times, LiveMint),
runs VADER sentiment scoring in pure Python, and computes aggregated
NewsFlag per symbol/sector with parallel verification.

All calculations are pure Python. NO LLM numeric work.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
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
            # Finance lexicon extensions
            _finance_lexicon = {
                "bullish": 2.0, "bearish": -2.0, "rally": 1.5, "crash": -2.5,
                "surge": 1.8, "plunge": -2.0, "outperform": 1.5, "underperform": -1.5,
                "upgrade": 1.5, "downgrade": -1.5, "buy": 1.0, "sell": -1.0,
                "breakout": 1.3, "breakdown": -1.3, "recovery": 1.2, "correction": -1.0,
                "profit": 1.0, "loss": -1.0, "growth": 1.0, "decline": -1.0,
                "dividend": 0.8, "debt": -0.5, "acquisition": 0.6, "layoff": -1.0,
                "expansion": 0.8, "restructuring": -0.3, "earnings": 0.5,
                "npa": -1.5, "default": -2.0, "scam": -2.5, "fraud": -2.5,
            }
            _vader_analyzer.lexicon.update(_finance_lexicon)
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
# RSS Feed Configuration — grouped by provider for parallel verification
# ---------------------------------------------------------------------------

NewsFlag = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]

# Provider grouping for cross-verification
PROVIDER_1_FEEDS = [
    {"name": "MoneyControl", "url": "https://www.moneycontrol.com/rss/MCtopnews.xml", "provider": "P1"},
    {"name": "MoneyControl_Markets", "url": "https://www.moneycontrol.com/rss/marketreports.xml", "provider": "P1"},
]
PROVIDER_2_FEEDS = [
    {"name": "ET_Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "provider": "P2"},
    {"name": "ET_Stocks", "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms", "provider": "P2"},
]
PROVIDER_3_FEEDS = [
    {"name": "LiveMint", "url": "https://www.livemint.com/rss/markets", "provider": "P3"},
]

RSS_FEEDS = PROVIDER_1_FEEDS + PROVIDER_2_FEEDS + PROVIDER_3_FEEDS

# Configurable thresholds
SENTIMENT_POSITIVE_THRESHOLD = 0.25   # Raised to match spec (>0.25)
SENTIMENT_NEGATIVE_THRESHOLD = -0.25  # Raised to match spec (<-0.25)
SENTIMENT_TOLERANCE = 0.35  # Cross-source verification tolerance
MIN_NEWS_COUNT_FOR_FLAG = 2
NEWS_LOOKBACK_HOURS = 12

# In-memory cache for news items
_news_cache: dict[str, list[dict]] = {}
_news_cache_ts: float = 0.0
NEWS_CACHE_TTL_SECONDS = 600  # 10 minutes

# NEWS_AGGREGATE in-memory cache (90s TTL per symbol)
_agg_cache: dict[str, dict] = {}
_agg_cache_ts: dict[str, float] = {}
AGG_CACHE_TTL_SECONDS = 90

# Previous news flags for NEWS_IMPACT detection (in-memory, 5min TTL)
_prev_news_flags: dict[str, tuple[str, float]] = {}

# Continuous monitor state
_monitor_task: asyncio.Task | None = None
_monitor_running = False


# ---------------------------------------------------------------------------
# 4.1  News Fetching with Parallel Verification (Batch 4 Item 1)
# ---------------------------------------------------------------------------

def _headline_hash(title: str) -> str:
    """Normalize and hash a headline for cross-source dedup."""
    normalized = re.sub(r"[^a-z0-9\s]", "", title.lower().strip())
    # Remove very short words and common fillers
    words = [w for w in normalized.split() if len(w) > 2]
    return hashlib.sha256(" ".join(sorted(words[:8])).encode()).hexdigest()[:12]


def _fetch_rss_headlines(max_per_feed: int = 30) -> list[dict[str, Any]]:
    """
    Fetch headlines from all configured RSS feeds.
    Returns list of {title, summary, published, source, provider, link, sentiment_score}.
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
                summary = re.sub(r"<[^>]+>", "", summary).strip()

                all_items.append({
                    "title": title,
                    "summary": summary[:300],
                    "published": published or now,
                    "source": feed_cfg["name"],
                    "provider": feed_cfg.get("provider", "P1"),
                    "link": getattr(entry, "link", ""),
                    "headline_hash": _headline_hash(title),
                })
        except Exception as e:
            logger.warning(f"RSS fetch failed for {feed_cfg['name']}: {e}")

    return all_items


def _score_headline(title: str, summary: str = "") -> float:
    """
    Score a single headline using VADER sentiment with finance lexicon.
    Returns compound score in [-1.0, +1.0].
    """
    analyzer = _get_vader()
    if analyzer is None:
        return 0.0

    text = f"{title}. {summary}" if summary else title
    scores = analyzer.polarity_scores(text)
    return scores.get("compound", 0.0)


def _parallel_verify(items: list[dict]) -> list[dict]:
    """
    Cross-source verification of headlines.

    Headlines found in 2+ providers → VERIFIED (weight 1.0x)
    Headlines in 1 provider only → SINGLE_SOURCE (weight 0.7x)
    Headlines with sentiment disagreement > TOLERANCE → UNVERIFIED (excluded)
    """
    # Group by headline_hash
    hash_groups: dict[str, list[dict]] = {}
    for item in items:
        h = item["headline_hash"]
        if h not in hash_groups:
            hash_groups[h] = []
        hash_groups[h].append(item)

    verified_items: list[dict] = []

    for h, group in hash_groups.items():
        providers = set(item["provider"] for item in group)

        if len(providers) >= 2:
            # Multi-source: check sentiment agreement
            scores = [item.get("sentiment_score", 0.0) for item in group]
            if max(scores) - min(scores) > SENTIMENT_TOLERANCE:
                # Sentiment disagreement → UNVERIFIED
                for item in group:
                    item["verification_status"] = "UNVERIFIED"
                    item["source_count"] = len(providers)
                logger.debug(f"UNVERIFIED headline: sentiment_diff={max(scores)-min(scores):.2f}")
            else:
                # Agreement → VERIFIED, use averaged score
                avg_score = sum(scores) / len(scores)
                best = group[0].copy()
                best["sentiment_score"] = round(avg_score, 4)
                best["verification_status"] = "VERIFIED"
                best["source_count"] = len(providers)
                best["source_weight"] = 1.0
                verified_items.append(best)
        else:
            # Single source
            item = group[0].copy()
            item["verification_status"] = "SINGLE_SOURCE"
            item["source_count"] = 1
            item["source_weight"] = 0.7
            verified_items.append(item)

    return verified_items


def _match_symbol_in_text(text: str, symbol: str) -> bool:
    """Check if a symbol name appears in headline/summary text."""
    text_upper = text.upper()
    if symbol.upper() in text_upper:
        return True
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
# Recency weighting (Batch 4 Item 1)
# ---------------------------------------------------------------------------

def _recency_weight(published: datetime) -> float:
    """Weight headlines by freshness."""
    age_mins = (datetime.now(timezone.utc) - published).total_seconds() / 60
    if age_mins <= 30:
        return 1.00
    if age_mins <= 60:
        return 0.80
    if age_mins <= 120:
        return 0.60
    if age_mins <= 240:
        return 0.35
    return 0.10


# ---------------------------------------------------------------------------
# 4.2  NEWS_FETCH and refresh (updated with parallel verification)
# ---------------------------------------------------------------------------

def refresh_news_cache() -> int:
    """
    Refresh the news headline cache from RSS feeds with parallel verification.
    Returns number of verified items.
    """
    global _news_cache, _news_cache_ts

    now = time.time()
    if now - _news_cache_ts < NEWS_CACHE_TTL_SECONDS and _news_cache:
        return sum(len(v) for v in _news_cache.values())

    raw_items = _fetch_rss_headlines()
    if not raw_items:
        return 0

    # Score each headline
    for item in raw_items:
        item["sentiment_score"] = round(
            _score_headline(item["title"], item.get("summary", "")), 4
        )

    # Parallel verification
    verified = _parallel_verify(raw_items)

    _news_cache = {"all": verified}
    _news_cache_ts = now
    logger.info(f"News cache refreshed: {len(verified)} verified headlines (from {len(raw_items)} raw)")
    return len(verified)


def news_fetch(symbol: str, sector: str | None = None) -> list[dict]:
    """
    NEWS_FETCH(symbol, sector): Fetch and verify headlines for a symbol.

    Returns list of verified/single_source headlines matching symbol or sector.
    Each item has: {title, summary, published, source, provider, sentiment_score,
                    verification_status, source_count, source_weight}
    """
    if not _news_cache or (time.time() - _news_cache_ts) > NEWS_CACHE_TTL_SECONDS:
        refresh_news_cache()

    all_items = _news_cache.get("all", [])
    matched: list[dict] = []

    for item in all_items:
        # Exclude UNVERIFIED
        if item.get("verification_status") == "UNVERIFIED":
            continue

        text = f"{item.get('title', '')} {item.get('summary', '')}"
        if _match_symbol_in_text(text, symbol):
            matched.append(item)
        elif sector and _match_sector_in_text(text, sector):
            matched.append(item)

    return matched


# ---------------------------------------------------------------------------
# 4.3  NEWS_AGGREGATE (Batch 4 Item 2)
# ---------------------------------------------------------------------------

def news_aggregate(symbol: str, sector: str | None = None) -> dict[str, Any]:
    """
    NEWS_AGGREGATE(symbol): Aggregated sentiment with recency weighting.

    Uses 4-hour window (2 hours if near market close).
    Returns: {news_flag, avg_sentiment, recent_news_count, headline_summary, last_refreshed_at}
    """
    # Check 90s cache
    now = time.time()
    cached = _agg_cache.get(symbol)
    cached_ts = _agg_cache_ts.get(symbol, 0)
    if cached and (now - cached_ts) < AGG_CACHE_TTL_SECONDS:
        return cached

    headlines = news_fetch(symbol, sector)

    # Determine window: 4 hours normally, 2 hours if within 60 mins of 15:30 IST
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    mins_to_close = (market_close - now_ist).total_seconds() / 60

    window_hours = 2 if 0 < mins_to_close <= 60 else 4
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    windowed = [
        h for h in headlines
        if h.get("published") and h["published"] >= cutoff
    ]

    if not windowed:
        result = {
            "symbol": symbol,
            "news_flag": "NEUTRAL",
            "avg_sentiment": 0.0,
            "recent_news_count": 0,
            "headline_summary": "No recent news",
            "last_refreshed_at": now_ist.isoformat(),
        }
        _agg_cache[symbol] = result
        _agg_cache_ts[symbol] = now
        return result

    # Weighted average: recency_weight × source_weight
    values = []
    weights = []
    for h in windowed:
        s = h.get("sentiment_score", 0.0)
        rw = _recency_weight(h["published"])
        sw = h.get("source_weight", 0.7)
        values.append(s)
        weights.append(rw * sw)

    total_w = sum(weights)
    avg_sentiment = sum(v * w for v, w in zip(values, weights)) / total_w if total_w > 0 else 0.0

    # Determine news_flag
    if avg_sentiment > SENTIMENT_POSITIVE_THRESHOLD and len(windowed) >= MIN_NEWS_COUNT_FOR_FLAG:
        news_flag: NewsFlag = "POSITIVE"
    elif avg_sentiment < SENTIMENT_NEGATIVE_THRESHOLD and len(windowed) >= MIN_NEWS_COUNT_FOR_FLAG:
        news_flag = "NEGATIVE"
    else:
        news_flag = "NEUTRAL"

    # Top 2 most recent verified headlines
    sorted_recent = sorted(windowed, key=lambda x: x.get("published", datetime.min), reverse=True)
    headline_summary = "; ".join(
        h["title"][:120] for h in sorted_recent[:2]
    )

    result = {
        "symbol": symbol,
        "news_flag": news_flag,
        "avg_sentiment": round(avg_sentiment, 4),
        "recent_news_count": len(windowed),
        "headline_summary": headline_summary,
        "last_refreshed_at": now_ist.isoformat(),
    }

    _agg_cache[symbol] = result
    _agg_cache_ts[symbol] = now
    return result


# ---------------------------------------------------------------------------
# Legacy API (kept for backward compatibility)
# ---------------------------------------------------------------------------

def get_symbol_sentiment(
    symbol: str,
    lookback_hours: int = NEWS_LOOKBACK_HOURS,
) -> dict[str, Any]:
    """
    Get aggregated sentiment for a specific symbol (legacy API).
    Now delegates to news_aggregate for consistency.
    """
    agg = news_aggregate(symbol)
    return {
        "symbol": symbol,
        "news_count": agg.get("recent_news_count", 0),
        "avg_sentiment": agg.get("avg_sentiment", 0.0),
        "news_flag": agg.get("news_flag", "NEUTRAL"),
        "headlines": [],  # Legacy field
    }


def get_sector_sentiment(
    sector: str,
    lookback_hours: int = NEWS_LOOKBACK_HOURS,
) -> dict[str, Any]:
    """Get aggregated sentiment for a sector."""
    if not _news_cache or (time.time() - _news_cache_ts) > NEWS_CACHE_TTL_SECONDS:
        refresh_news_cache()

    all_items = _news_cache.get("all", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    relevant: list[dict] = []
    for item in all_items:
        if item.get("verification_status") == "UNVERIFIED":
            continue
        pub = item.get("published")
        if pub and pub < cutoff:
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        if _match_sector_in_text(text, sector):
            relevant.append(item)

    if not relevant:
        return {"sector": sector, "news_count": 0, "avg_sentiment": 0.0, "news_flag": "NEUTRAL"}

    scores = [item.get("sentiment_score", 0.0) for item in relevant]
    avg_sent = sum(scores) / len(scores) if scores else 0.0

    if avg_sent > SENTIMENT_POSITIVE_THRESHOLD and len(relevant) >= MIN_NEWS_COUNT_FOR_FLAG:
        flag: NewsFlag = "POSITIVE"
    elif avg_sent < SENTIMENT_NEGATIVE_THRESHOLD and len(relevant) >= MIN_NEWS_COUNT_FOR_FLAG:
        flag = "NEGATIVE"
    else:
        flag = "NEUTRAL"

    return {"sector": sector, "news_count": len(relevant), "avg_sentiment": round(avg_sent, 3), "news_flag": flag}


def get_market_sentiment_summary() -> dict[str, Any]:
    """Get overall market sentiment from all cached headlines."""
    if not _news_cache or (time.time() - _news_cache_ts) > NEWS_CACHE_TTL_SECONDS:
        refresh_news_cache()

    all_items = _news_cache.get("all", [])
    if not all_items:
        return {"total_headlines": 0, "avg_sentiment": 0.0, "market_flag": "NEUTRAL",
                "positive_pct": 0.0, "negative_pct": 0.0}

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

    return {"total_headlines": len(all_items), "avg_sentiment": round(avg, 3),
            "market_flag": market_flag, "positive_pct": round(positive, 1),
            "negative_pct": round(negative, 1)}


# ---------------------------------------------------------------------------
# 4.4  Continuous Monitor Background Task (Batch 4 Item 3)
# ---------------------------------------------------------------------------

def get_prev_news_flag(symbol: str) -> str | None:
    """Get previous news flag for NEWS_IMPACT detection."""
    entry = _prev_news_flags.get(symbol)
    if entry is None:
        return None
    flag, ts = entry
    # TTL: 5 minutes
    if time.time() - ts > 300:
        return None
    return flag


def set_prev_news_flag(symbol: str, flag: str) -> None:
    """Store current news flag as previous for next cycle."""
    _prev_news_flags[symbol] = (flag, time.time())


def _is_market_hours() -> bool:
    """Check if current time is within 09:15-15:30 IST on a weekday."""
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


async def continuous_monitor_cycle(watch_list: list[str], event_callback=None) -> dict:
    """
    Single cycle of the continuous monitor.
    Checks news changes for all symbols in watch_list.

    Returns: {checked: int, events_emitted: int}
    """
    events_emitted = 0
    checked = 0

    # Force-refresh news cache for this cycle
    refresh_news_cache()

    for symbol in watch_list:
        try:
            prev_flag = get_prev_news_flag(symbol)
            curr_result = news_aggregate(symbol)
            curr_flag = curr_result.get("news_flag", "NEUTRAL")

            # Store for next cycle
            set_prev_news_flag(symbol, curr_flag)
            checked += 1

            # Emit NEWS_IMPACT if flag changed adversely (callback handled externally)
            if event_callback and prev_flag and prev_flag != curr_flag:
                await event_callback(symbol, prev_flag, curr_flag, curr_result)
                events_emitted += 1

        except Exception as e:
            logger.warning(f"NEWS_FETCH failed for {symbol}: {e}")
            # Maintain last known flag, do NOT crash
            continue

    return {"checked": checked, "events_emitted": events_emitted}


async def start_continuous_monitor(
    get_watch_list_fn,
    event_callback=None,
    poll_interval: int | None = None,
):
    """
    Start the async continuous monitor background loop.
    Runs during market hours only, every NEWS_POLL_INTERVAL_SECS.
    """
    global _monitor_running
    _monitor_running = True

    interval = poll_interval or int(os.environ.get("NEWS_POLL_INTERVAL_SECS", "120"))
    logger.info(f"News continuous monitor started (interval={interval}s)")

    while _monitor_running:
        try:
            if _is_market_hours():
                watch_list = await get_watch_list_fn() if asyncio.iscoroutinefunction(get_watch_list_fn) else get_watch_list_fn()
                # Always include indices
                base = {"NIFTY", "BANKNIFTY"}
                full_list = list(base | set(watch_list))
                result = await continuous_monitor_cycle(full_list, event_callback)
                logger.debug(f"Monitor cycle: checked={result['checked']}, events={result['events_emitted']}")
            else:
                logger.debug("News monitor: outside market hours, sleeping")
        except Exception as e:
            logger.error(f"News monitor cycle error: {e}")

        await asyncio.sleep(interval)


def stop_continuous_monitor():
    """Signal the continuous monitor to stop."""
    global _monitor_running
    _monitor_running = False
    logger.info("News continuous monitor stopped")

