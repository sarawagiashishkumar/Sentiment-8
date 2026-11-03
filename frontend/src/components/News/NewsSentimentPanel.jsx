import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { Button } from "components/ui/button";
import { TrendingUp, TrendingDown, Minus, RefreshCw, Newspaper } from "lucide-react";

const API = "/api";

const BIAS_STYLE = {
  BULLISH: { icon: TrendingUp, color: "text-emerald-400", bg: "bg-emerald-950/30 border-emerald-700/40" },
  BEARISH: { icon: TrendingDown, color: "text-rose-400", bg: "bg-rose-950/30 border-rose-700/40" },
  NEUTRAL: { icon: Minus, color: "text-slate-400", bg: "bg-slate-800/50 border-slate-700" },
};

export function NewsSentimentPanel({ authHeaders }) {
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [symbolNews, setSymbolNews] = useState(null);

  const fetchForecast = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/news/forecast`, { headers: authHeaders });
      setForecast(res.data);
    } catch (err) { console.error("Forecast fetch error:", err?.message); }
    finally { setLoading(false); }
  }, [authHeaders]);

  useEffect(() => { fetchForecast(); }, [fetchForecast]);

  const fetchSymbolNews = async (e) => {
    e.preventDefault();
    const sym = symbolSearch.trim().toUpperCase();
    if (!sym) return;
    try {
      const res = await axios.get(`${API}/news/symbol/${sym}`, { headers: authHeaders });
      setSymbolNews(res.data);
    } catch (err) { console.error(err); }
  };

  const sessionLabel = { pre_market: "Pre-Market", post_market: "Post-Market", intraday: "Intraday" };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="news-sentiment-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2 text-sm">
          <Newspaper size={16} className="text-amber-400" /> News & Sentiment
          {forecast && <span className="text-[10px] font-normal text-slate-400 bg-slate-800 px-2 py-0.5 rounded">{sessionLabel[forecast.session] || forecast.session}</span>}
        </CardTitle>
        <Button onClick={fetchForecast} disabled={loading} className="h-7 bg-amber-600 text-white hover:bg-amber-500 text-xs px-3" data-testid="news-refresh-btn">
          <RefreshCw size={12} className={`mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Index Forecasts */}
        {forecast?.index_forecasts && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="index-forecasts">
            {Object.entries(forecast.index_forecasts).map(([idx, data]) => {
              const style = BIAS_STYLE[data.bias] || BIAS_STYLE.NEUTRAL;
              const Icon = style.icon;
              return (
                <div key={idx} className={`rounded-lg border p-3 ${style.bg}`} data-testid={`forecast-${idx}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-bold text-white">{idx}</span>
                    <div className="flex items-center gap-1">
                      <Icon size={14} className={style.color} />
                      <span className={`text-xs font-bold ${style.color}`}>{data.bias}</span>
                    </div>
                  </div>
                  <div className="flex gap-3 text-[10px] text-slate-400 mb-2">
                    <span>Score: <span className="font-mono text-white">{data.sentiment_score}</span></span>
                    <span>Headlines: {data.headline_count}</span>
                    {data.technical?.ltp && <span>LTP: <span className="font-mono text-cyan-300">{data.technical.ltp}</span></span>}
                    {data.technical?.rsi_14 && <span>RSI: {data.technical.rsi_14}</span>}
                    {data.technical?.trend_alignment && <span>Trend: {data.technical.trend_alignment}</span>}
                  </div>
                  {data.top_headlines?.length > 0 && (
                    <div className="space-y-1">
                      {data.top_headlines.slice(0, 3).map((h, i) => (
                        <p key={h.title || `hl-${i}`} className="text-[10px] text-slate-300 leading-tight">
                          <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${h.sentiment === "positive" ? "bg-emerald-400" : h.sentiment === "negative" ? "bg-rose-400" : "bg-slate-500"}`} />
                          {h.title}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Market Overview */}
        {forecast?.market_overview && (
          <div className="flex gap-3 text-[10px]" data-testid="market-overview">
            <span className="text-emerald-400">Bullish: {forecast.market_overview.bullish_count || 0}</span>
            <span className="text-rose-400">Bearish: {forecast.market_overview.bearish_count || 0}</span>
            <span className="text-slate-400">Neutral: {forecast.market_overview.neutral_count || 0}</span>
            <span className="text-slate-500">Total: {forecast.market_overview.total_headlines || 0}</span>
          </div>
        )}

        {/* Top Stock Sentiments */}
        {forecast?.top_stock_sentiments?.length > 0 && (
          <div data-testid="stock-sentiments">
            <p className="text-[10px] text-slate-400 font-semibold mb-1">Top F&O Stock Sentiments</p>
            <div className="flex flex-wrap gap-1.5">
              {forecast.top_stock_sentiments.map(s => {
                const style = BIAS_STYLE[s.bias] || BIAS_STYLE.NEUTRAL;
                return (
                  <span key={s.symbol} className={`rounded px-2 py-1 text-[10px] font-mono border ${style.bg} ${style.color}`} data-testid={`stock-sentiment-${s.symbol}`}>
                    {s.symbol} {s.composite_score > 0 ? "+" : ""}{s.composite_score}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Symbol Search */}
        <form onSubmit={fetchSymbolNews} className="flex gap-2" data-testid="news-symbol-search">
          <input
            type="text" value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)}
            placeholder="Search symbol (e.g. RELIANCE)..."
            className="flex-1 h-8 rounded-md border border-slate-700 bg-slate-900 px-3 text-xs text-slate-100 focus:border-amber-500 focus:outline-none"
            data-testid="news-search-input"
          />
          <Button type="submit" className="h-8 bg-amber-600 text-white hover:bg-amber-500 text-xs px-3" data-testid="news-search-btn">Search</Button>
        </form>

        {symbolNews && (
          <div className="space-y-2" data-testid="symbol-news-results">
            <p className="text-xs font-bold text-white">{symbolNews.symbol} — {symbolNews.headlines?.length || 0} headlines</p>
            {symbolNews.sentiment && (
              <div className="flex gap-2 text-[10px]">
                <span className="text-slate-400">Score: <span className="font-mono text-white">{symbolNews.sentiment.composite_score?.toFixed(3)}</span></span>
                <span className="text-slate-400">Label: <span className={symbolNews.sentiment.composite_score > 0.3 ? "text-emerald-400" : symbolNews.sentiment.composite_score < -0.3 ? "text-rose-400" : "text-slate-300"}>
                  {symbolNews.sentiment.composite_score > 0.3 ? "BULLISH" : symbolNews.sentiment.composite_score < -0.3 ? "BEARISH" : "NEUTRAL"}
                </span></span>
              </div>
            )}
            {symbolNews.headlines?.slice(0, 10).map((h, i) => (
              <div key={i} className="rounded border border-slate-700 bg-slate-900/50 px-2 py-1.5">
                <p className="text-[10px] text-slate-200">{h.title}</p>
                <div className="flex gap-2 text-[9px] text-slate-500 mt-0.5">
                  <span>{h.source}</span>
                  <span className={h.sentiment_label === "positive" ? "text-emerald-400" : h.sentiment_label === "negative" ? "text-rose-400" : ""}>{h.sentiment_label}</span>
                  {h.published && <span>{new Date(h.published).toLocaleDateString("en-IN")}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
