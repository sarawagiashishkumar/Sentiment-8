import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { Activity, LayoutGrid, List, Search, X } from "lucide-react";
import { RefreshCountdown } from "@/components/Shared/RefreshCountdown";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

const INDEX_TABS = [
  { id: "nifty", label: "NIFTY" },
  { id: "banknifty", label: "BANKNIFTY" },
];

const TOP_FNO_STOCKS = [
  { id: "RELIANCE", label: "RELIANCE" },
  { id: "TCS", label: "TCS" },
  { id: "HDFCBANK", label: "HDFCBANK" },
];

export function OptionsHeatmap({ authHeaders, onFetchError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeSymbol, setActiveSymbol] = useState("nifty");
  const [customStock, setCustomStock] = useState("");
  const [searchSuggestions, setSearchSuggestions] = useState([]);
  const [oiTypeFilter, setOiTypeFilter] = useState("all");
  const [viewMode, setViewMode] = useState("treemap");
  const [minOI, setMinOI] = useState(0);
  const intervalRef = useRef(null);
  const symbolRef = useRef(activeSymbol);
  const searchTimeoutRef = useRef(null);

  const loadData = useCallback(async (symbol, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const resp = await axios.get(`${API}/market/options-heatmap?filter=${symbol}`, { headers: authHeaders });
      setData(resp.data);
      if (!resp.data.kite_live && onFetchError) onFetchError();
    } catch {
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  }, [authHeaders, onFetchError]);

  useEffect(() => { loadData(activeSymbol); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    symbolRef.current = activeSymbol;
    loadData(activeSymbol);
  }, [activeSymbol, loadData]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadData(symbolRef.current, true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  // Instant search — zero-click auto-populate
  const handleSearchInput = (value) => {
    setCustomStock(value);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    const q = value.trim().toUpperCase();
    if (q.length >= 2) {
      // Auto-suggest from known F&O symbols
      const knownSymbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK", "BAJFINANCE", "WIPRO", "HINDUNILVR", "BHARTIARTL", "TATAMOTORS", "MARUTI", "M&M", "SUNPHARMA", "TITAN", "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "COALINDIA", "NTPC", "POWERGRID", "ONGC", "HCLTECH", "TECHM", "ULTRACEMCO", "NESTLEIND", "CIPLA", "DRREDDY", "DIVISLAB", "APOLLOHOSP", "HEROMOTOCO", "EICHERMOT", "BPCL", "TRENT", "HINDALCO", "SHRIRAMFIN", "DLF", "INDIGO", "HAL", "BEL", "ZOMATO", "PAYTM", "LIC", "DMART", "TATAPOWER", "VEDL"];
      const matches = knownSymbols.filter(s => s.includes(q)).slice(0, 5);
      setSearchSuggestions(matches);
      // Zero-click: if exact match, fetch immediately
      if (matches.length === 1 && matches[0] === q) {
        searchTimeoutRef.current = setTimeout(() => {
          setActiveSymbol(q);
          setCustomStock("");
          setSearchSuggestions([]);
        }, 300);
      }
    } else {
      setSearchSuggestions([]);
    }
  };

  const selectSuggestion = (sym) => {
    setActiveSymbol(sym);
    setCustomStock("");
    setSearchSuggestions([]);
  };

  const handleCustomSearch = (e) => {
    e.preventDefault();
    const sym = customStock.trim().toUpperCase();
    if (sym) { setActiveSymbol(sym); setCustomStock(""); setSearchSuggestions([]); }
  };

  const chains = data?.chains || [];

  // Build flat contracts for treemap
  const allContracts = [];
  chains.forEach(item => {
    (item.strikes || []).forEach(row => {
      if (oiTypeFilter === "all" || oiTypeFilter === "ce") {
        if (row.ce_ltp != null) {
          const oi = row.ce_oi || 0;
          if (oi >= minOI) {
            allContracts.push({
              ts: row.ce_ts || `${item.symbol}${row.strike}CE`,
              type: "CE", strike: row.strike, ltp: row.ce_ltp, oi, iv: row.ce_iv,
              symbol: item.symbol, spot: item.spot,
            });
          }
        }
      }
      if (oiTypeFilter === "all" || oiTypeFilter === "pe") {
        if (row.pe_ltp != null) {
          const oi = row.pe_oi || 0;
          if (oi >= minOI) {
            allContracts.push({
              ts: row.pe_ts || `${item.symbol}${row.strike}PE`,
              type: "PE", strike: row.strike, ltp: row.pe_ltp, oi, iv: row.pe_iv,
              symbol: item.symbol, spot: item.spot,
            });
          }
        }
      }
    });
  });
  allContracts.sort((a, b) => (b.oi || 0) - (a.oi || 0));

  // Available expiries
  const availableExpiries = chains.length > 0 ? (chains[0].available_expiries || []) : [];

  if (loading && !data) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-8">
        <p className="text-sm text-slate-400 text-center animate-pulse" data-testid="options-loading">Loading options data...</p>
      </div>
    );
  }

  // Determine if current selection is an index or stock
  const isIndexTab = INDEX_TABS.some(t => t.id === activeSymbol);
  const isTopStock = TOP_FNO_STOCKS.some(t => t.id === activeSymbol);

  return (
    <div className="space-y-3" data-testid="options-heatmap">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" />
          Options Heatmap
        </h2>
        <RefreshCountdown intervalMs={REFRESH_INTERVAL} isActive={true} onManualRefresh={() => loadData(activeSymbol)} />
      </div>

      {/* Row 1: NIFTY / BANKNIFTY Tabs */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="options-index-tabs">
        {INDEX_TABS.map(t => (
          <button key={t.id} data-testid={`options-tab-${t.id}`}
            onClick={() => setActiveSymbol(t.id)}
            className={`rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
              activeSymbol === t.id
                ? "bg-cyan-600 text-white shadow-lg shadow-cyan-500/20"
                : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
            }`}>{t.label}</button>
        ))}
        <div className="w-px h-5 bg-slate-700" />
        {/* ALL / CE / PE filter */}
        {["all", "ce", "pe"].map(t => (
          <button key={t} data-testid={`options-oi-type-${t}`}
            onClick={() => setOiTypeFilter(t)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              oiTypeFilter === t
                ? "bg-cyan-600 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}>{t.toUpperCase()}</button>
        ))}
        <div className="w-px h-5 bg-slate-700" />
        {/* Expiry dropdown */}
        {availableExpiries.length > 0 && (
          <select
            className="bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-300 focus:border-cyan-500 focus:outline-none"
            data-testid="options-expiry-select"
            defaultValue=""
          >
            <option value="">All Expiries</option>
            {availableExpiries.map(exp => (
              <option key={exp} value={exp}>{exp}</option>
            ))}
          </select>
        )}
      </div>

      {/* Row 2: Top 3 F&O Stocks + Custom Symbol Search */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="options-stock-filters">
        {TOP_FNO_STOCKS.map(f => (
          <button key={f.id} data-testid={`options-stock-${f.id.toLowerCase()}`}
            onClick={() => setActiveSymbol(f.id)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              activeSymbol === f.id
                ? "bg-emerald-600 text-white"
                : "text-slate-400 hover:text-slate-200 bg-slate-800/50"
            }`}>{f.label}</button>
        ))}

        {/* Custom stock search with auto-suggest */}
        <div className="relative" data-testid="options-custom-search">
          <form onSubmit={handleCustomSearch} className="flex items-center gap-1">
            <div className="relative">
              <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={customStock}
                onChange={(e) => handleSearchInput(e.target.value)}
                placeholder="Search F&O symbol..."
                className="bg-slate-900 border border-slate-700 rounded-md pl-6 pr-6 py-1 text-xs text-slate-200 w-40 focus:border-cyan-500 focus:outline-none"
                data-testid="options-custom-stock-input"
              />
              {customStock && (
                <button type="button" onClick={() => { setCustomStock(""); setSearchSuggestions([]); }} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  <X size={11} />
                </button>
              )}
            </div>
          </form>
          {/* Auto-suggest dropdown */}
          {searchSuggestions.length > 0 && (
            <div className="absolute top-full left-0 mt-1 w-40 bg-slate-900 border border-slate-700 rounded-md shadow-xl z-20" data-testid="options-search-suggestions">
              {searchSuggestions.map(sym => (
                <button
                  key={sym}
                  onClick={() => selectSuggestion(sym)}
                  className="w-full text-left px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 font-mono"
                  data-testid={`options-suggest-${sym.toLowerCase()}`}
                >
                  {sym}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Active symbol indicator */}
        {!isIndexTab && !isTopStock && activeSymbol && (
          <span className="rounded bg-violet-600 px-2 py-0.5 text-xs font-mono text-white" data-testid="options-active-custom">
            {activeSymbol}
          </span>
        )}

        {/* Min OI slider */}
        <div className="flex items-center gap-1 text-[10px] text-slate-400 ml-auto">
          <Activity size={10} />
          <span>Min OI:</span>
          <input
            type="range" min="0" max="50000" step="1000" value={minOI}
            onChange={(e) => setMinOI(Number(e.target.value))}
            className="w-16 h-1 accent-cyan-500"
            data-testid="options-min-oi-slider"
          />
          <span className="font-mono text-slate-300 w-6 text-right">{minOI > 0 ? `${(minOI/1000).toFixed(0)}K` : "0"}</span>
        </div>

        {/* View toggle */}
        <div className="flex border border-slate-700 rounded-md overflow-hidden">
          <button data-testid="options-view-treemap" onClick={() => setViewMode("treemap")}
            className={`p-1.5 ${viewMode === "treemap" ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
            <LayoutGrid size={13} />
          </button>
          <button data-testid="options-view-chain" onClick={() => setViewMode("chain")}
            className={`p-1.5 ${viewMode === "chain" ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
            <List size={13} />
          </button>
        </div>
      </div>

      {/* Contract count */}
      <div className="text-right">
        <span className="text-xs text-slate-500 font-mono" data-testid="options-contract-count">{allContracts.length} contracts</span>
      </div>

      {data?.warning && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="options-warning">{data.warning}</div>
      )}

      {/* Summary */}
      {data?.summary && data.summary.pcr != null && (
        <div className="flex flex-wrap gap-2 text-xs" data-testid="options-summary">
          <span className="rounded bg-slate-800 px-2 py-1 text-slate-300 font-mono">PCR: {data.summary.pcr}</span>
          {data.summary.oi_buildup && (
            <span className={`rounded px-2 py-1 font-semibold ${
              data.summary.oi_buildup === "LONG_BUILDUP" ? "bg-emerald-900/50 text-emerald-300" :
              data.summary.oi_buildup === "SHORT_BUILDUP" ? "bg-rose-900/50 text-rose-300" :
              "bg-slate-800 text-slate-300"
            }`}>{data.summary.oi_buildup.replace(/_/g, " ")}</span>
          )}
        </div>
      )}

      {/* Treemap View */}
      {data && viewMode === "treemap" && allContracts.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-9 gap-px bg-slate-800 rounded-lg overflow-hidden" data-testid="options-treemap-view">
          {allContracts.slice(0, 500).map((c, idx) => {
            const isCE = c.type === "CE";
            const bgCls = isCE
              ? "bg-gradient-to-br from-emerald-800/80 to-teal-900/70"
              : "bg-gradient-to-br from-purple-800/80 to-pink-900/70";
            return (
              <div key={`${c.ts}-${idx}`}
                data-testid={`option-tile-${idx}`}
                className={`${bgCls} p-2 flex flex-col items-center justify-center text-white transition-all hover:brightness-125`}
                title={`OI: ${c.oi ? (c.oi/1000).toFixed(0) + 'K' : '0'} | IV: ${c.iv?.toFixed(1) || '--'}`}
              >
                <span className="font-mono text-[7px] text-slate-300 truncate w-full text-center">{c.ts}</span>
                <span className="font-mono text-sm font-bold mt-0.5">
                  Rs.{c.ltp?.toFixed(2) || "0"}
                </span>
                <span className="font-mono text-[8px] text-slate-400 mt-0.5">
                  OI: {c.oi ? (c.oi/1000).toFixed(0) + 'K' : '0'}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Chain View */}
      {data && viewMode === "chain" && chains.length > 0 && (
        <div className="space-y-3" data-testid="options-chain-view">
          {chains.map(item => (
            <div key={item.symbol} className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono font-semibold text-sm text-slate-100">{item.symbol}</span>
                <div className="flex gap-3 text-xs text-slate-400">
                  <span>Spot: <span className="text-cyan-300 font-mono">{item.spot?.toFixed(2)}</span></span>
                  {item.expiry && <span>Exp: {item.expiry}</span>}
                </div>
              </div>
              {item.strikes?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-[10px]" data-testid="options-chain-table">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-700">
                        <th className="px-2 py-1.5 text-right">CE OI</th>
                        <th className="px-2 py-1.5 text-right">CE IV</th>
                        <th className="px-2 py-1.5 text-right">CE LTP</th>
                        <th className="px-2 py-1.5 text-center font-bold text-cyan-400">Strike</th>
                        <th className="px-2 py-1.5 text-left">PE LTP</th>
                        <th className="px-2 py-1.5 text-left">PE IV</th>
                        <th className="px-2 py-1.5 text-left">PE OI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {item.strikes.filter(row => {
                        if (oiTypeFilter === "ce") return row.ce_ltp != null;
                        if (oiTypeFilter === "pe") return row.pe_ltp != null;
                        return true;
                      }).filter(row => Math.max(row.ce_oi || 0, row.pe_oi || 0) >= minOI
                      ).map(row => {
                        const isATM = Math.abs(row.strike - item.spot) <= (item.step || 50);
                        return (
                          <tr key={row.strike} className={isATM ? "bg-cyan-900/20 font-bold" : "hover:bg-slate-800/40"}>
                            <td className="px-2 py-1 text-right font-mono text-emerald-400">{row.ce_oi ? (row.ce_oi / 1000).toFixed(0) + "K" : "--"}</td>
                            <td className="px-2 py-1 text-right font-mono text-violet-300">{row.ce_iv?.toFixed(1) || "--"}</td>
                            <td className="px-2 py-1 text-right font-mono text-slate-200">{row.ce_ltp?.toFixed(2) || "--"}</td>
                            <td className={`px-2 py-1 text-center font-mono ${isATM ? "text-cyan-300 text-xs" : "text-slate-400"}`}>{row.strike}</td>
                            <td className="px-2 py-1 text-left font-mono text-slate-200">{row.pe_ltp?.toFixed(2) || "--"}</td>
                            <td className="px-2 py-1 text-left font-mono text-violet-300">{row.pe_iv?.toFixed(1) || "--"}</td>
                            <td className="px-2 py-1 text-left font-mono text-rose-400">{row.pe_oi ? (row.pe_oi / 1000).toFixed(0) + "K" : "--"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-slate-500 text-center py-2">No option chain data.</p>
              )}
            </div>
          ))}
        </div>
      )}

      {data && allContracts.length === 0 && chains.length === 0 && !loading && (
        <p className="text-sm text-slate-400 text-center py-4" data-testid="options-no-data">No options data. Ensure Market Data API is connected.</p>
      )}
    </div>
  );
}
