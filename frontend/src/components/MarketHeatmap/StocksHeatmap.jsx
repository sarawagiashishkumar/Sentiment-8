import { useState, useMemo } from "react";
import axios from "axios";
import { Filter, RefreshCw, LayoutGrid, List } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ALARM_URL = "https://cdn.pixabay.com/download/audio/2022/03/25/audio_25c0b2671e.mp3?filename=freesound_community-alarm-106447.mp3";

const FILTER_PRESETS = [
  { id: "fno", label: "F&O Universe" },
  { id: "nifty50", label: "Nifty 50" },
  { id: "banknifty", label: "BankNifty" },
  { id: "all", label: "All Stocks" },
  { id: "plus5", label: "+5% Gainers" },
  { id: "plus3", label: "+3% Gainers" },
  { id: "minus3", label: "-3% Losers" },
  { id: "minus5", label: "-5% Losers" },
];

const VIEW_MODES = [
  { id: "treemap", label: "Treemap", icon: LayoutGrid },
  { id: "list", label: "List View", icon: List },
];

function getChangeColor(pct) {
  if (pct >= 5) return "bg-emerald-500 text-white";
  if (pct >= 3) return "bg-emerald-600 text-white";
  if (pct >= 1) return "bg-emerald-700/80 text-emerald-100";
  if (pct >= 0) return "bg-emerald-900/50 text-emerald-200";
  if (pct >= -1) return "bg-rose-900/50 text-rose-200";
  if (pct >= -3) return "bg-rose-700/80 text-rose-100";
  if (pct >= -5) return "bg-rose-600 text-white";
  return "bg-rose-500 text-white";
}

function TreemapTile({ stock }) {
  const absPct = Math.abs(stock.change_pct || 0);
  const minH = absPct >= 5 ? 80 : absPct >= 3 ? 68 : absPct >= 1 ? 56 : 48;
  return (
    <div
      data-testid={`stock-tile-${stock.symbol.toLowerCase()}`}
      className={`rounded-lg ${getChangeColor(stock.change_pct)} flex flex-col items-center justify-center px-2 py-2 cursor-default transition-all hover:brightness-110 hover:scale-[1.03] border border-white/10`}
      style={{ minWidth: "90px", minHeight: `${minH}px`, flex: "1 1 90px", maxWidth: "140px" }}
      title={`${stock.symbol}: ₹${stock.ltp?.toFixed(2) || 0} (${stock.change_pct >= 0 ? "+" : ""}${stock.change_pct?.toFixed(2)}%)`}
    >
      <span className="font-mono text-[11px] font-bold leading-tight truncate w-full text-center">{stock.symbol}</span>
      <span className="font-mono text-sm font-bold mt-0.5">{stock.change_pct >= 0 ? "+" : ""}{stock.change_pct?.toFixed(2)}%</span>
      {stock.ltp > 0 && <span className="text-[9px] opacity-70 mt-0.5">₹{stock.ltp.toFixed(0)}</span>}
    </div>
  );
}

function ListRow({ stock, idx }) {
  return (
    <tr className={`${idx % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"} hover:bg-slate-800/60`}>
      <td className="px-3 py-1.5 font-mono text-xs font-semibold text-slate-200">{stock.symbol}</td>
      <td className="px-3 py-1.5 text-xs text-right font-mono">₹{stock.ltp?.toFixed(2) || "0"}</td>
      <td className={`px-3 py-1.5 text-xs text-right font-mono font-bold ${stock.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
        {stock.change_pct >= 0 ? "+" : ""}{stock.change_pct?.toFixed(2)}%
      </td>
      <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">₹{stock.prev_close?.toFixed(2) || "0"}</td>
    </tr>
  );
}

export function StocksHeatmap({ authHeaders, onFetchError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeFilter, setActiveFilter] = useState("fno");
  const [viewMode, setViewMode] = useState("treemap");
  const [listPage, setListPage] = useState(0);
  const PAGE_SIZE = 50;

  const loadData = async () => {
    setError("");
    setLoading(true);
    try {
      const resp = await axios.get(`${API}/market/stock-heatmap?filter=${activeFilter}`, { headers: authHeaders });
      setData(resp.data);
      if (!resp.data.kite_live && onFetchError) onFetchError();
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load stock heatmap");
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  };

  const stocks = data?.stocks || [];
  const gainers = stocks.filter((s) => s.change_pct > 0).length;
  const losers = stocks.filter((s) => s.change_pct < 0).length;
  const liveCount = stocks.filter((s) => s.ltp > 0).length;

  const pagedStocks = useMemo(() => {
    const start = listPage * PAGE_SIZE;
    return stocks.slice(start, start + PAGE_SIZE);
  }, [stocks, listPage]);
  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="stocks-heatmap">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 flex-wrap">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          <Filter size={14} />
          Stocks Heatmap
        </CardTitle>
        <div className="flex items-center gap-2">
          <div className="flex border border-slate-700 rounded-md overflow-hidden">
            {VIEW_MODES.map((v) => (
              <button
                key={v.id}
                data-testid={`stocks-view-${v.id}`}
                onClick={() => setViewMode(v.id)}
                className={`flex items-center gap-1 px-2.5 py-1 text-[10px] font-medium transition-all ${
                  viewMode === v.id ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <v.icon size={12} />
                {v.label}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={loadData} disabled={loading} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="stocks-heatmap-load">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {loading ? "Loading..." : data ? "Refresh" : "Load Heatmap"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-3 flex flex-wrap gap-1" data-testid="stocks-heatmap-filters">
          {FILTER_PRESETS.map((f) => (
            <button
              key={f.id}
              data-testid={`stocks-filter-${f.id}`}
              onClick={() => { setActiveFilter(f.id); setListPage(0); }}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
                activeFilter === f.id
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
                  : "text-slate-400 border border-slate-700 hover:text-slate-200 hover:border-slate-500"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {error && <p className="text-sm text-rose-400 mb-3" data-testid="stocks-heatmap-error">{error}</p>}
        {data && !data.kite_live && (
          <div className="mb-3 rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="stocks-heatmap-no-live">
            No live API data available. Ensure market data API is authenticated in Admin panel.
          </div>
        )}
        {!data && !loading && (
          <p className="text-sm text-slate-400 py-6 text-center">Select a filter and click <strong>Load Heatmap</strong>.</p>
        )}
        {data && (
          <>
            <div className="mb-3 flex gap-3 text-xs">
              <span className="text-emerald-400 font-semibold">{gainers} Gainers</span>
              <span className="text-rose-400 font-semibold">{losers} Losers</span>
              <span className="text-slate-400">{stocks.length} Total</span>
              <span className="text-cyan-400">{liveCount} Live</span>
            </div>

            {viewMode === "treemap" ? (
              <div className="flex flex-wrap gap-1.5" data-testid="stocks-heatmap-grid">
                {stocks.map((s) => <TreemapTile key={s.symbol} stock={s} />)}
              </div>
            ) : (
              <div>
                <div className="overflow-x-auto rounded-lg border border-slate-700">
                  <table className="w-full text-xs" data-testid="stocks-heatmap-list">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400">
                        <th className="px-3 py-2 text-left font-medium">Symbol</th>
                        <th className="px-3 py-2 text-right font-medium">LTP</th>
                        <th className="px-3 py-2 text-right font-medium">Change %</th>
                        <th className="px-3 py-2 text-right font-medium">Prev Close</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedStocks.map((s, i) => <ListRow key={s.symbol} stock={s} idx={i} />)}
                    </tbody>
                  </table>
                </div>
                {totalPages > 1 && (
                  <div className="flex justify-center gap-2 mt-3">
                    <button onClick={() => setListPage(Math.max(0, listPage - 1))} disabled={listPage === 0} className="rounded px-3 py-1 text-xs border border-slate-700 text-slate-300 disabled:opacity-30">Prev</button>
                    <span className="text-xs text-slate-400 py-1">Page {listPage + 1} / {totalPages}</span>
                    <button onClick={() => setListPage(Math.min(totalPages - 1, listPage + 1))} disabled={listPage >= totalPages - 1} className="rounded px-3 py-1 text-xs border border-slate-700 text-slate-300 disabled:opacity-30">Next</button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
