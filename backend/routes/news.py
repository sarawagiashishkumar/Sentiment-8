"""
News & Sentiment route handlers.

Pre-market/post-market forecasts, symbol sentiment, sector sentiment, 
and market-wide sentiment summary.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query

from deps import get_current_user
import services.app_state as _state

logger = logging.getLogger(__name__)

news_router = APIRouter()


@news_router.get("/news/market-summary")
async def get_market_sentiment_summary_endpoint(user=Depends(get_current_user)):
    """Get aggregated market-wide sentiment summary (bullish/bearish/neutral counts)."""
    from services.news_sentiment import get_market_sentiment_summary
    return get_market_sentiment_summary()


@news_router.get("/news/symbol/{symbol}")
async def get_symbol_news(symbol: str, user=Depends(get_current_user)):
    """Get news headlines and sentiment for a specific symbol."""
    from services.news_sentiment import news_fetch, get_symbol_sentiment
    headlines = news_fetch(symbol.upper())
    sentiment = get_symbol_sentiment(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "headlines": headlines[:20],
        "sentiment": sentiment,
    }


@news_router.get("/news/sector/{sector}")
async def get_sector_news(sector: str, user=Depends(get_current_user)):
    """Get sector-level sentiment analysis."""
    from services.news_sentiment import get_sector_sentiment
    return get_sector_sentiment(sector)


@news_router.get("/news/forecast")
async def get_market_forecast(user=Depends(get_current_user)):
    """
    Pre-market / post-market forecast for NIFTY, BANKNIFTY, and top F&O stocks.
    Combines sentiment analysis with technical context for directional bias.
    """
    from services.news_sentiment import (
        get_market_sentiment_summary,
        get_symbol_sentiment,
        news_fetch,
    )

    now = datetime.now(_state.IST)
    hour = now.hour
    is_pre_market = hour < 9 or (hour == 9 and now.minute < 15)
    is_post_market = hour >= 15 and now.minute >= 30
    session = "pre_market" if is_pre_market else ("post_market" if is_post_market else "intraday")

    market_summary = get_market_sentiment_summary()

    # Key indices
    indices = ["NIFTY", "BANKNIFTY"]
    index_forecasts = {}
    for idx in indices:
        sentiment = get_symbol_sentiment(idx)
        headlines = news_fetch(idx)[:5]

        # Directional bias from sentiment
        score = sentiment.get("composite_score", 0) if sentiment else 0
        if score > 0.3:
            bias = "BULLISH"
        elif score < -0.3:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        # Enrich with cache data if available
        cache_doc = None
        if _state.db is not None:
            cache_doc = await _state.db.equity_master_cache.find_one(
                {"symbol": idx}, {"_id": 0, "ltp": 1, "rsi_14_daily": 1, "trend_alignment": 1, "regime_label": 1, "supertrend_signal": 1}
            )

        technical_context = {}
        if cache_doc:
            rsi = cache_doc.get("rsi_14_daily")
            trend = cache_doc.get("trend_alignment")
            if rsi and rsi > 70:
                bias = "BEARISH" if bias == "NEUTRAL" else bias
            elif rsi and rsi < 30:
                bias = "BULLISH" if bias == "NEUTRAL" else bias
            technical_context = {
                "ltp": cache_doc.get("ltp"),
                "rsi_14": rsi,
                "trend_alignment": trend,
                "regime": cache_doc.get("regime_label"),
                "supertrend": cache_doc.get("supertrend_signal"),
            }

        index_forecasts[idx] = {
            "bias": bias,
            "sentiment_score": round(score, 3),
            "headline_count": len(headlines),
            "top_headlines": [{"title": h.get("title", ""), "sentiment": h.get("sentiment_label", "neutral")} for h in headlines],
            "technical": technical_context,
        }

    # Top F&O stocks sentiment
    top_stocks = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "BAJFINANCE"]
    stock_sentiments = []
    for sym in top_stocks:
        s = get_symbol_sentiment(sym)
        if s:
            stock_sentiments.append({
                "symbol": sym,
                "composite_score": round(s.get("composite_score", 0), 3),
                "bias": "BULLISH" if s.get("composite_score", 0) > 0.3 else ("BEARISH" if s.get("composite_score", 0) < -0.3 else "NEUTRAL"),
                "headline_count": s.get("headline_count", 0),
            })

    # Sort by absolute sentiment strength
    stock_sentiments.sort(key=lambda x: abs(x["composite_score"]), reverse=True)

    return {
        "session": session,
        "timestamp": now.isoformat(),
        "market_overview": market_summary,
        "index_forecasts": index_forecasts,
        "top_stock_sentiments": stock_sentiments[:10],
        "data_source": "rss_sentiment_engine",
    }


@news_router.get("/news/refresh")
async def refresh_news_cache_endpoint(user=Depends(get_current_user)):
    """Force refresh the news cache."""
    from services.news_sentiment import refresh_news_cache
    count = refresh_news_cache()
    return {"refreshed": True, "headlines_cached": count}
