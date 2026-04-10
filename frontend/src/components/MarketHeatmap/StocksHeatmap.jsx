import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import axios from "axios";
import { LayoutGrid, List } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

const FILTERS = [
  { id: "nifty50", label: "NIFTY50" },
  { id: "banknifty", label: "BANKNIFTY" },
  { id: "all", label: "ALL" },
];

function getTileColor(pct) {
  if (pct >= 4) return "bg-emerald-500";
  if (pct >= 2) return "bg-emerald-600/90";
  if (pct >= 1) return "bg-emerald-700/70";
  if (pct >= 0.3) return "bg-emerald-800/60";
  if (pct >= 0) return "bg-emerald-900/40";
  if (pct >= -1) return "bg-rose-900/50";
  if (pct >= -2) return "bg-rose-800/60";
  if (pct >= -4) return "bg-rose-700/70";
  return "bg-rose-600";
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

  useEffect(() => { loadData(activeFilter); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    filterRef.current = activeFilter;
    setListPage(0);
    loadData(activeFilter);
  }, [activeFilter, loadData]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadData(filterRef.current, true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  const stocks = data?.stocks || [];
  const pagedStocks = useMemo(() => {
    const start = listPage * PAGE_SIZE;
    return stocks.slice(start, start + PAGE_SIZE);
  }, [stocks, listPage]);
  const totalPages = Math.ceil(stocks.length / PAGE_SIZE);

  if (loading && !data) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-8">
        <p className="text-sm text-slate-400 text-center animate-pulse">Loading stock data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="stocks-heatmap">
      <h2 className="text-lg font-bold text-white">Stocks Heatmap</h2>

      {/* Filter bar - matches reference: filters, toggle, color bar, count */}
      <div className="flex items-center gap-3 flex-wrap" data-testid="stocks-heatmap-filters">
        {/* Filter pills */}
        <div className="flex items-center gap-1">
          {FILTERS.map(f => (
            <button key={f.id} data-testid={`stocks-filter-${f.id}`}
              onClick={() => setActiveFilter(f.id)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
                activeFilter === f.id
                  ? "bg-cyan-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >{f.label}</button>
          ))}
        </div>

        {/* View toggle */}
        <div className="flex border border-slate-700 rounded-md overflow-hidden">
          <button data-testid="stocks-view-treemap" onClick={() => setViewMode("treemap")}
            className={`p-1.5 ${viewMode === "treemap" ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
            <LayoutGrid size={14} />
          </button>
          <button data-testid="stocks-view-list" onClick={() => setViewMode("list")}
            className={`p-1.5 ${viewMode === "list" ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
            <List size={14} />
          </button>
        </div>

        {/* Color range */}
        <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
          <span>-10%</span>
          <div className="w-32 h-1.5 rounded-full bg-gradient-to-r from-rose-600 via-slate-600 to-emerald-500" />
          <span>10%</span>
        </div>

        {/* Stock count */}
        <span className="ml-auto text-xs text-slate-500 font-mono" data-testid="stocks-count">{stocks.length} stocks</span>
      </div>

      {data && !data.kite_live && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="stocks-heatmap-no-live">
          API not connected. Ensure market data is authenticated in Admin panel.
        </div>
      )}

      {/* Treemap View - true treemap filling entire width */}
      {data && stocks.length > 0 && viewMode === "treemap" && (
        <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-11 gap-px bg-slate-800 rounded-lg overflow-hidden" data-testid="stocks-heatmap-grid">
          {stocks.map(s => (
            <div
              key={s.symbol}
              data-testid={`stock-tile-${s.symbol.toLowerCase()}`}
              className={`${getTileColor(s.change_pct)} p-2 flex flex-col items-center justify-center text-white transition-all hover:brightness-125`}
              title={`${s.symbol}: Rs.${s.ltp?.toFixed(2) || 0} (${s.change_pct >= 0 ? "+" : ""}${s.change_pct?.toFixed(2)}%)`}
            >
              <span className="font-mono text-[9px] font-bold truncate w-full text-center">{s.symbol}</span>
              {s.ltp > 0 && <span className="text-[8px] opacity-70 font-mono">Rs.{s.ltp.toFixed(1)}</span>}
              <span className="font-mono text-xs font-bold">{s.change_pct >= 0 ? "+" : ""}{s.change_pct?.toFixed(2)}%</span>
            </div>
          ))}
        </div>
      )}

      {/* List View */}
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
                {pagedStocks.map((s, i) => (
                  <tr key={s.symbol} className={`${i % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"} hover:bg-slate-800/60`}>
                    <td className="px-3 py-1.5 font-mono text-xs font-semibold text-slate-200">{s.symbol}</td>
                    <td className="px-3 py-1.5 text-xs text-right font-mono">Rs.{s.ltp?.toFixed(2) || "0"}</td>
                    <td className={`px-3 py-1.5 text-xs text-right font-mono font-bold ${s.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {s.change_pct >= 0 ? "+" : ""}{s.change_pct?.toFixed(2)}%
                    </td>
                    <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">Rs.{s.prev_close?.toFixed(2) || "0"}</td>
                  </tr>
                ))}
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
    </div>
  );
}
