import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { Activity, LayoutGrid, List, Search } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

const SYMBOL_PRESETS = [
  { id: "nifty", label: "NIFTY" },
  { id: "banknifty", label: "BANKNIFTY" },
  { id: "RELIANCE", label: "RELIANCE" },
  { id: "TCS", label: "TCS" },
  { id: "HDFCBANK", label: "HDFCBANK" },
];

export function OptionsHeatmap({ authHeaders, onFetchError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeSymbol, setActiveSymbol] = useState("nifty");
  const [customStock, setCustomStock] = useState("");
  const [oiTypeFilter, setOiTypeFilter] = useState("all");
  const [viewMode, setViewMode] = useState("treemap");
  const [minOI, setMinOI] = useState(0);
  const intervalRef = useRef(null);
  const symbolRef = useRef(activeSymbol);

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

  const handleCustomSearch = (e) => {
    e.preventDefault();
    const sym = customStock.trim().toUpperCase();
    if (sym) { setActiveSymbol(sym); setCustomStock(""); }
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
        <p className="text-sm text-slate-400 text-center animate-pulse">Loading options data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="options-heatmap">
      <h2 className="text-lg font-bold text-white flex items-center gap-2">
        <Activity size={18} className="text-cyan-400" />
        Options Heatmap
      </h2>

      {/* Single filter row - matching reference layout exactly */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="options-heatmap-filters">
        {/* Symbol presets */}
        {SYMBOL_PRESETS.map(f => (
          <button key={f.id} data-testid={`options-filter-${f.id}`}
            onClick={() => setActiveSymbol(f.id)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              activeSymbol === f.id
                ? "bg-cyan-600 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}>{f.label}</button>
        ))}

        {/* Separator */}
        <div className="w-px h-5 bg-slate-700" />

        {/* ALL / CE / PE */}
        {["all", "ce", "pe"].map(t => (
          <button key={t} data-testid={`options-oi-type-${t}`}
            onClick={() => setOiTypeFilter(t)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              oiTypeFilter === t
                ? "bg-cyan-600 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}>{t.toUpperCase()}</button>
        ))}

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

        {/* Custom Stock */}
        <form onSubmit={handleCustomSearch} className="flex items-center gap-1">
          <input
            type="text"
            value={customStock}
            onChange={(e) => setCustomStock(e.target.value)}
            placeholder="Custom Stock..."
            className="bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 w-28 focus:border-cyan-500 focus:outline-none"
            data-testid="options-custom-stock-input"
          />
          <button type="submit" className="text-slate-400 hover:text-cyan-300 p-1" data-testid="options-custom-stock-search">
            <Search size={12} />
          </button>
        </form>

        {/* Min OI */}
        <div className="flex items-center gap-1 text-[10px] text-slate-400">
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
        <div className="flex border border-slate-700 rounded-md overflow-hidden ml-auto">
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
        <div className="rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300">{data.warning}</div>
      )}

      {/* Summary */}
      {data?.summary && data.summary.pcr != null && (
        <div className="flex flex-wrap gap-2 text-xs">
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

      {/* Treemap View - matches reference: CE=teal, PE=magenta/pink, full width grid */}
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
                  <table className="w-full text-[10px]">
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
        <p className="text-sm text-slate-400 text-center py-4">No options data. Ensure API is connected.</p>
      )}
    </div>
  );
}
