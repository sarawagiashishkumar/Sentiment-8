import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import axios from "axios";
import { LayoutGrid, List, Search, X } from "lucide-react";
import { RefreshCountdown } from "@/components/Shared/RefreshCountdown";
import { HeatmapSkeleton } from "@/components/Shared/Skeletons";

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
  { id: "all", label: "ALL F&O" },
];

function getTileColor(pct) {
  const absVal = Math.abs(pct);
  const intensity = Math.min(absVal / 5, 1);
  const opacity = 0.2 + intensity * 0.75;
  if (pct >= 0) {
    return `rgba(16, 185, 129, ${opacity})`;
  }
  return `rgba(239, 68, 68, ${opacity})`;
}

export function StocksHeatmap({ authHeaders, onFetchError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeFilter, setActiveFilter] = useState("nifty50");
  const [viewMode, setViewMode] = useState("treemap");
  const [listPage, setListPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [changeRange, setChangeRange] = useState([0, 0]);
  const [sliderValue, setSliderValue] = useState([0, 0]);
  const intervalRef = useRef(null);
  const filterRef = useRef(activeFilter);
  const PAGE_SIZE = 50;

  const loadData = useCallback(async (filter, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const resp = await axios.get(`${API}/market/stock-heatmap?filter=${filter}`, { headers: authHeaders });
      setData(resp.data);
      // Compute dynamic range from actual data
      const stocks = resp.data?.stocks || [];
      if (stocks.length > 0) {
        const pcts = stocks.map(s => s.change_pct || 0);
        const minPct = Math.floor(Math.min(...pcts));
        const maxPct = Math.ceil(Math.max(...pcts));
        setChangeRange([minPct, maxPct]);
        setSliderValue([minPct, maxPct]);
      }
      if (!resp.data.kite_live && onFetchError) onFetchError();
    } catch (err) {
      console.error("StocksHeatmap fetch error:", err);
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  }, [authHeaders, onFetchError]);

  useEffect(() => { loadData(activeFilter); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    filterRef.current = activeFilter;
    setListPage(0);
    setSearchQuery("");
    loadData(activeFilter);
  }, [activeFilter, loadData]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadData(filterRef.current, true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  // Filter stocks by search and slider range
  const filteredStocks = useMemo(() => {
    let stocks = data?.stocks || [];
    // Apply change % range filter
    stocks = stocks.filter(s => s.change_pct >= sliderValue[0] && s.change_pct <= sliderValue[1]);
    // Apply search filter (instant, zero-click)
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toUpperCase();
      stocks = stocks.filter(s => s.symbol.includes(q));
    }
    return stocks;
  }, [data, sliderValue, searchQuery]);

  const pagedStocks = useMemo(() => {
    const start = listPage * PAGE_SIZE;
    return filteredStocks.slice(start, start + PAGE_SIZE);
  }, [filteredStocks, listPage]);
  const totalPages = Math.ceil(filteredStocks.length / PAGE_SIZE);

  if (loading && !data) {
    return <HeatmapSkeleton />;
  }

  return (
    <div className="space-y-3" data-testid="stocks-heatmap">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">Stocks Heatmap</h2>
        <RefreshCountdown intervalMs={REFRESH_INTERVAL} isActive={true} onManualRefresh={() => loadData(activeFilter)} />
      </div>

      {/* Filter bar */}
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

        {/* Instant Symbol Search */}
        <div className="relative flex items-center" data-testid="stocks-search-container">
          <Search size={12} className="absolute left-2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setListPage(0); }}
            placeholder="Search symbol..."
            className="bg-slate-900 border border-slate-700 rounded-md pl-7 pr-7 py-1 text-xs text-slate-200 w-36 focus:border-cyan-500 focus:outline-none"
            data-testid="stocks-search-input"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")} className="absolute right-1.5 text-slate-500 hover:text-slate-300" data-testid="stocks-search-clear">
              <X size={12} />
            </button>
          )}
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

        {/* Stock count */}
        <span className="ml-auto text-xs text-slate-500 font-mono" data-testid="stocks-count">
          {filteredStocks.length}{filteredStocks.length !== (data?.stocks?.length || 0) ? ` / ${data?.stocks?.length || 0}` : ""} stocks
        </span>
      </div>

      {/* Dynamic Change % Slider */}
      {changeRange[0] !== changeRange[1] && (
        <div className="flex items-center gap-3 flex-wrap" data-testid="stocks-change-slider">
          <span className="text-[10px] text-slate-500 font-mono w-14 text-right">{sliderValue[0].toFixed(1)}%</span>
          <div className="flex-1 max-w-xs relative">
            <div className="w-full h-1.5 rounded-full bg-gradient-to-r from-rose-600 via-slate-600 to-emerald-500" />
            <input
              type="range"
              min={changeRange[0]}
              max={changeRange[1]}
              step={0.1}
              value={sliderValue[0]}
              onChange={(e) => setSliderValue([Number(e.target.value), sliderValue[1]])}
              className="absolute top-0 left-0 w-full h-1.5 appearance-none bg-transparent pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400 [&::-webkit-slider-thumb]:cursor-pointer"
              data-testid="stocks-slider-min"
            />
            <input
              type="range"
              min={changeRange[0]}
              max={changeRange[1]}
              step={0.1}
              value={sliderValue[1]}
              onChange={(e) => setSliderValue([sliderValue[0], Number(e.target.value)])}
              className="absolute top-0 left-0 w-full h-1.5 appearance-none bg-transparent pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400 [&::-webkit-slider-thumb]:cursor-pointer"
              data-testid="stocks-slider-max"
            />
          </div>
          <span className="text-[10px] text-slate-500 font-mono w-14">{sliderValue[1].toFixed(1)}%</span>
          {(sliderValue[0] !== changeRange[0] || sliderValue[1] !== changeRange[1]) && (
            <button
              onClick={() => setSliderValue([changeRange[0], changeRange[1]])}
              className="text-[10px] text-cyan-400 hover:text-cyan-300"
              data-testid="stocks-slider-reset"
            >
              Reset
            </button>
          )}
        </div>
      )}

      {data && !data.kite_live && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="stocks-heatmap-no-live">
          Market Data API not connected. Ensure data source is authenticated in Admin panel.
        </div>
      )}

      {/* Treemap View - gradient intensity colors */}
      {data && filteredStocks.length > 0 && viewMode === "treemap" && (
        <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-11 gap-px bg-slate-800 rounded-lg overflow-hidden" data-testid="stocks-heatmap-grid">
          {filteredStocks.map(s => (
            <div
              key={s.symbol}
              data-testid={`stock-tile-${s.symbol.toLowerCase()}`}
              className="p-2 flex flex-col items-center justify-center text-white transition-all hover:brightness-125"
              style={{ backgroundColor: getTileColor(s.change_pct) }}
              title={`${s.symbol}: Rs.${s.ltp?.toFixed(2) || 0} (${s.change_pct >= 0 ? "+" : ""}${s.change_pct?.toFixed(2)}%)`}
            >
              <span className="font-mono text-[9px] font-bold truncate w-full text-center">{s.symbol}</span>
              {s.ltp > 0 && <span className="text-[8px] opacity-70 font-mono">Rs.{s.ltp.toFixed(1)}</span>}
              <span className="font-mono text-xs font-bold">{s.change_pct >= 0 ? "+" : ""}{s.change_pct?.toFixed(2)}%</span>
            </div>
          ))}
        </div>
      )}

      {/* List View - Full detail */}
      {data && filteredStocks.length > 0 && viewMode === "list" && (
        <div>
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table className="w-full text-xs" data-testid="stocks-heatmap-list">
              <thead>
                <tr className="bg-slate-800/80 text-slate-400">
                  <th className="px-3 py-2 text-left font-medium">Symbol</th>
                  <th className="px-3 py-2 text-right font-medium">LTP</th>
                  <th className="px-3 py-2 text-right font-medium">Change %</th>
                  <th className="px-3 py-2 text-right font-medium">Open</th>
                  <th className="px-3 py-2 text-right font-medium">High</th>
                  <th className="px-3 py-2 text-right font-medium">Low</th>
                  <th className="px-3 py-2 text-right font-medium">Volume</th>
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
                    <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">{s.open > 0 ? `Rs.${s.open.toFixed(2)}` : "--"}</td>
                    <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">{s.high > 0 ? `Rs.${s.high.toFixed(2)}` : "--"}</td>
                    <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">{s.low > 0 ? `Rs.${s.low.toFixed(2)}` : "--"}</td>
                    <td className="px-3 py-1.5 text-xs text-right font-mono text-slate-400">{s.volume > 0 ? s.volume.toLocaleString("en-IN") : "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-3">
              <button onClick={() => setListPage(Math.max(0, listPage - 1))} disabled={listPage === 0} className="rounded px-3 py-1 text-xs border border-slate-700 text-slate-300 disabled:opacity-30" data-testid="stocks-list-prev">Prev</button>
              <span className="text-xs text-slate-400 py-1">Page {listPage + 1} / {totalPages}</span>
              <button onClick={() => setListPage(Math.min(totalPages - 1, listPage + 1))} disabled={listPage >= totalPages - 1} className="rounded px-3 py-1 text-xs border border-slate-700 text-slate-300 disabled:opacity-30" data-testid="stocks-list-next">Next</button>
            </div>
          )}
        </div>
      )}

      {data && filteredStocks.length === 0 && !loading && (
        <p className="text-sm text-slate-400 py-4 text-center" data-testid="stocks-no-results">No stocks match the selected filters.</p>
      )}
    </div>
  );
}
