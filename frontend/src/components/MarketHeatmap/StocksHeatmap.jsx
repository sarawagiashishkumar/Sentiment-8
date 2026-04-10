import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import axios from "axios";
import { RefreshCw, LayoutGrid, List } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

const FILTER_PRESETS = [
  { id: "nifty50", label: "NIFTY50" },
  { id: "banknifty", label: "BANKNIFTY" },
  { id: "fno", label: "F&O Universe" },
  { id: "all", label: "ALL" },
  { id: "plus5", label: "+5%" },
  { id: "plus3", label: "+3%" },
  { id: "minus3", label: "-3%" },
  { id: "minus5", label: "-5%" },
];

function getChangeColor(pct) {
  if (pct >= 5) return "bg-emerald-500 text-white";
  if (pct >= 3) return "bg-emerald-600/90 text-white";
  if (pct >= 1) return "bg-emerald-700/70 text-emerald-100";
  if (pct >= 0) return "bg-emerald-900/40 text-emerald-200";
  if (pct >= -1) return "bg-rose-900/40 text-rose-200";
  if (pct >= -3) return "bg-rose-700/70 text-rose-100";
  if (pct >= -5) return "bg-rose-600/90 text-white";
  return "bg-rose-500 text-white";
}

function TreemapTile({ stock }) {
  return (
    <div
      data-testid={`stock-tile-${stock.symbol.toLowerCase()}`}
      className={`rounded-lg ${getChangeColor(stock.change_pct)} flex flex-col items-center justify-center px-2 py-2 transition-all hover:brightness-110 hover:scale-[1.02] border border-white/10`}
      style={{ flex: "1 1 110px", minWidth: "100px", maxWidth: "160px", minHeight: "65px" }}
      title={`${stock.symbol}: ${stock.ltp > 0 ? `Rs.${stock.ltp.toFixed(2)}` : ""} (${stock.change_pct >= 0 ? "+" : ""}${stock.change_pct?.toFixed(2)}%)`}
    >
      <span className="font-mono text-[10px] font-bold truncate w-full text-center">{stock.symbol}</span>
      {stock.ltp > 0 && <span className="text-[9px] opacity-80 font-mono mt-0.5">Rs.{stock.ltp.toFixed(1)}</span>}
      <span className="font-mono text-sm font-bold">{stock.change_pct >= 0 ? "+" : ""}{stock.change_pct?.toFixed(2)}%</span>
    </div>
  );
}

function ListRow({ stock, idx }) {
  return (
    <tr className={`${idx % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"} hover:bg-slate-800/60`}>
      <td className="px-3 py-1.5 font-mono text-xs font-semibold text-slate-200">{stock.symbol}</td>
      <td className="px-3 py-1.5 text-xs text-right font-mono">Rs.{stock.ltp?.toFixed(2) || "0"}</td>
      <td className={`px-3 py-1.5 text-xs text-right font-mono font-bold ${stock.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
        {stock.change_pct >= 0 ? "+" : ""}{stock.change_pct?.toFixed(2)}%
      </td>
      <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">Rs.{stock.prev_close?.toFixed(2) || "0"}</td>
    </tr>
  );
}

export function StocksHeatmap({ authHeaders, onFetchError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeFilter, setActiveFilter] = useState("nifty50");
  const [viewMode, setViewMode] = useState("treemap");
  const [listPage, setListPage] = useState(0);
  const intervalRef = useRef(null);
  const filterRef = useRef(activeFilter);
  const PAGE_SIZE = 50;

  const loadData = useCallback(async (filter, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const resp = await axios.get(`${API}/market/stock-heatmap?filter=${filter}`, { headers: authHeaders });
      setData(resp.data);
      if (!resp.data.kite_live && onFetchError) onFetchError();
    } catch {
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  }, [authHeaders, onFetchError]);

  // Auto-fetch on mount
  useEffect(() => {
    loadData(activeFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-reload when filter changes
  useEffect(() => {
    filterRef.current = activeFilter;
    setListPage(0);
    loadData(activeFilter);
  }, [activeFilter, loadData]);

  // Auto-refresh during market hours
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadData(filterRef.current, true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  const stocks = data?.stocks || [];
  const gainers = stocks.filter(s => s.change_pct > 0).length;
  const losers = stocks.filter(s => s.change_pct < 0).length;

  const pagedStocks = useMemo(() => {
    const start = listPage * PAGE_SIZE;
    return stocks.slice(start, start + PAGE_SIZE);
  }, [stocks, listPage]);
  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="stocks-heatmap">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 flex-wrap pb-3">
        <CardTitle className="text-white text-base">Stocks Heatmap</CardTitle>
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex border border-slate-700 rounded-md overflow-hidden">
            <button data-testid="stocks-view-treemap" onClick={() => setViewMode("treemap")}
              className={`p-1.5 transition-all ${viewMode === "treemap" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-slate-200"}`}>
              <LayoutGrid size={14} />
            </button>
            <button data-testid="stocks-view-list" onClick={() => setViewMode("list")}
              className={`p-1.5 transition-all ${viewMode === "list" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-slate-200"}`}>
              <List size={14} />
            </button>
          </div>
          {/* Stock count */}
          <span className="text-[10px] text-slate-500 font-mono">{stocks.length} stocks</span>
        </div>
      </CardHeader>
      <CardContent>
        {/* Filters */}
        <div className="mb-3 flex flex-wrap gap-1" data-testid="stocks-heatmap-filters">
          {FILTER_PRESETS.map(f => (
            <button key={f.id} data-testid={`stocks-filter-${f.id}`}
              onClick={() => setActiveFilter(f.id)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
                activeFilter === f.id
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
                  : "text-slate-400 border border-slate-700 hover:text-slate-200 hover:border-slate-500"
              }`}
            >{f.label}</button>
          ))}
        </div>

        {/* Color range indicator */}
        <div className="mb-3 flex items-center gap-2 text-[9px] text-slate-500">
          <span>-10%</span>
          <div className="flex-1 h-1.5 rounded-full bg-gradient-to-r from-rose-600 via-slate-600 to-emerald-600" />
          <span>10%</span>
          <span className="ml-2 text-emerald-400 font-semibold">{gainers} <span className="opacity-60">up</span></span>
          <span className="text-rose-400 font-semibold">{losers} <span className="opacity-60">down</span></span>
        </div>

        {loading && !data && (
          <div className="flex items-center justify-center gap-2 py-8 text-slate-400">
            <RefreshCw size={16} className="animate-spin" />
            <span className="text-sm">Loading stock data...</span>
          </div>
        )}

        {data && !data.kite_live && (
          <div className="mb-3 rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="stocks-heatmap-no-live">
            No live API data available. Ensure market data API is authenticated in Admin panel.
          </div>
        )}

        {data && stocks.length > 0 && viewMode === "treemap" && (
          <div className="flex flex-wrap gap-1.5" data-testid="stocks-heatmap-grid">
            {stocks.map(s => <TreemapTile key={s.symbol} stock={s} />)}
          </div>
        )}

        {data && stocks.length > 0 && viewMode === "list" && (
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

        {data && stocks.length === 0 && !loading && (
          <p className="text-sm text-slate-400 py-4 text-center">No stocks match the selected filter.</p>
        )}
      </CardContent>
    </Card>
  );
}
