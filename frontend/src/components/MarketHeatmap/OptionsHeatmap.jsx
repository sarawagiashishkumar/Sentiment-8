import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { Layers, RefreshCw, LayoutGrid, List, Search } from "lucide-react";
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

const SYMBOL_PRESETS = [
  { id: "nifty", label: "NIFTY" },
  { id: "banknifty", label: "BANKNIFTY" },
  { id: "RELIANCE", label: "RELIANCE" },
  { id: "TCS", label: "TCS" },
  { id: "HDFCBANK", label: "HDFCBANK" },
];

const OI_TYPE_FILTERS = [
  { id: "all", label: "ALL" },
  { id: "ce", label: "CE" },
  { id: "pe", label: "PE" },
];

const VIEW_MODES = [
  { id: "treemap", label: "Treemap", icon: LayoutGrid },
  { id: "chain", label: "Chain", icon: List },
];

function getOIColor(buildup) {
  if (buildup === "LONG_BUILDUP") return "bg-emerald-700/70 text-emerald-100";
  if (buildup === "SHORT_COVERING") return "bg-emerald-800/50 text-emerald-200";
  if (buildup === "SHORT_BUILDUP") return "bg-rose-700/70 text-rose-100";
  if (buildup === "LONG_UNWINDING") return "bg-rose-800/50 text-rose-200";
  return "bg-slate-800/60 text-slate-300";
}

function getStrikeBg(ceOI, peOI, pct) {
  if (pct > 0) return "border-emerald-600/30 bg-emerald-950/30";
  if (pct < -30) return "border-rose-500/40 bg-rose-950/40";
  if (pct < 0) return "border-rose-600/30 bg-rose-950/30";
  return "border-slate-700/40 bg-slate-900/40";
}

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

  // Auto-fetch on mount
  useEffect(() => {
    loadData(activeSymbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-reload when symbol changes
  useEffect(() => {
    symbolRef.current = activeSymbol;
    loadData(activeSymbol);
  }, [activeSymbol, loadData]);

  // Auto-refresh during market hours
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
    if (sym) {
      setActiveSymbol(sym);
      setCustomStock("");
    }
  };

  const chains = data?.chains || [];

  // Build flat option contracts list for treemap
  const allContracts = [];
  chains.forEach(item => {
    (item.strikes || []).forEach(row => {
      if (oiTypeFilter === "all" || oiTypeFilter === "ce") {
        if (row.ce_ltp != null) {
          const oi = row.ce_oi || 0;
          if (oi >= minOI) {
            const pct = row.ce_ltp && item.spot ? (((row.ce_ltp / (item.spot * 0.01)) - 1) * 100) : 0;
            allContracts.push({
              ts: row.ce_ts || `${item.symbol}${item.expiry || ""}${row.strike}CE`,
              type: "CE", strike: row.strike, ltp: row.ce_ltp, oi, iv: row.ce_iv,
              symbol: item.symbol, spot: item.spot, change_pct: pct,
            });
          }
        }
      }
      if (oiTypeFilter === "all" || oiTypeFilter === "pe") {
        if (row.pe_ltp != null) {
          const oi = row.pe_oi || 0;
          if (oi >= minOI) {
            const pct = row.pe_ltp && item.spot ? (((row.pe_ltp / (item.spot * 0.01)) - 1) * 100) : 0;
            allContracts.push({
              ts: row.pe_ts || `${item.symbol}${item.expiry || ""}${row.strike}PE`,
              type: "PE", strike: row.strike, ltp: row.pe_ltp, oi, iv: row.pe_iv,
              symbol: item.symbol, spot: item.spot, change_pct: pct,
            });
          }
        }
      }
    });
  });

  // Sort by OI desc for treemap
  allContracts.sort((a, b) => (b.oi || 0) - (a.oi || 0));

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="options-heatmap">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 flex-wrap pb-3">
        <CardTitle className="text-white text-base flex items-center gap-2">
          <Layers size={16} />
          Options Heatmap
        </CardTitle>
        <span className="text-[10px] text-slate-500 font-mono">{allContracts.length} contracts</span>
      </CardHeader>
      <CardContent>
        {/* Symbol filters */}
        <div className="mb-3 flex flex-wrap items-center gap-1.5" data-testid="options-heatmap-filters">
          {SYMBOL_PRESETS.map(f => (
            <button key={f.id} data-testid={`options-filter-${f.id}`}
              onClick={() => setActiveSymbol(f.id)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
                activeSymbol === f.id ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
                  : "text-slate-400 border border-slate-700 hover:text-slate-200 hover:border-slate-500"
              }`}>{f.label}</button>
          ))}

          {/* OI type filter */}
          <div className="flex border border-slate-700 rounded-md overflow-hidden ml-1">
            {OI_TYPE_FILTERS.map(f => (
              <button key={f.id} data-testid={`options-oi-type-${f.id}`}
                onClick={() => setOiTypeFilter(f.id)}
                className={`px-2 py-1 text-[10px] font-medium transition-all ${
                  oiTypeFilter === f.id ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-slate-200"
                }`}>{f.label}</button>
            ))}
          </div>

          {/* Custom stock search */}
          <form onSubmit={handleCustomSearch} className="flex items-center gap-1 ml-1">
            <input
              type="text"
              value={customStock}
              onChange={(e) => setCustomStock(e.target.value)}
              placeholder="Custom Stock..."
              className="bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-[10px] text-slate-200 w-24 focus:border-cyan-500/50 focus:outline-none"
              data-testid="options-custom-stock-input"
            />
            <button type="submit" className="text-slate-400 hover:text-cyan-300 p-1" data-testid="options-custom-stock-search">
              <Search size={12} />
            </button>
          </form>

          {/* Min OI filter */}
          <div className="flex items-center gap-1 ml-1 text-[10px] text-slate-400">
            <span>Min OI:</span>
            <input
              type="range" min="0" max="50000" step="1000" value={minOI}
              onChange={(e) => setMinOI(Number(e.target.value))}
              className="w-16 h-1 accent-cyan-500"
              data-testid="options-min-oi-slider"
            />
            <span className="font-mono text-slate-300 w-8">{minOI > 0 ? `${(minOI/1000).toFixed(0)}K` : "0"}</span>
          </div>

          {/* View mode */}
          <div className="flex border border-slate-700 rounded-md overflow-hidden ml-auto">
            {VIEW_MODES.map(v => (
              <button key={v.id} data-testid={`options-view-${v.id}`}
                onClick={() => setViewMode(v.id)}
                className={`p-1.5 transition-all ${
                  viewMode === v.id ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-slate-200"
                }`}><v.icon size={13} /></button>
            ))}
          </div>
        </div>

        {/* Summary */}
        {data?.summary && (data.summary.pcr != null || data.summary.oi_buildup) && (
          <div className="mb-3 flex flex-wrap gap-2 text-xs">
            {data.summary.pcr != null && <span className="rounded bg-slate-800 px-2 py-1 text-slate-300 font-mono">PCR: {data.summary.pcr}</span>}
            {data.summary.oi_buildup && (
              <span className={`rounded px-2 py-1 font-semibold ${getOIColor(data.summary.oi_buildup)}`}>
                {data.summary.oi_buildup.replace(/_/g, " ")}
              </span>
            )}
          </div>
        )}

        {data?.warning && (
          <div className="mb-3 rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300">{data.warning}</div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center gap-2 py-8 text-slate-400">
            <RefreshCw size={16} className="animate-spin" />
            <span className="text-sm">Loading options data...</span>
          </div>
        )}

        {/* Treemap View */}
        {data && viewMode === "treemap" && allContracts.length > 0 && (
          <div className="flex flex-wrap gap-1" data-testid="options-treemap-view">
            {allContracts.slice(0, 500).map((c, idx) => {
              const bgCls = c.type === "CE"
                ? "border-emerald-600/30 bg-emerald-950/30"
                : "border-rose-600/30 bg-rose-950/30";
              return (
                <div key={`${c.ts}-${idx}`}
                  className={`rounded-md border ${bgCls} flex flex-col items-center px-1.5 py-1.5 transition-all hover:brightness-110`}
                  style={{ flex: "1 1 110px", minWidth: "100px", maxWidth: "150px" }}
                  title={`OI: ${c.oi ? (c.oi/1000).toFixed(0) + 'K' : '0'} | IV: ${c.iv?.toFixed(1) || '-'}`}
                >
                  <span className="font-mono text-[8px] text-slate-400 truncate w-full text-center">{c.ts}</span>
                  <span className={`font-mono text-sm font-bold ${c.type === "CE" ? "text-emerald-300" : "text-rose-300"}`}>
                    Rs.{c.ltp?.toFixed(2) || "0"}
                  </span>
                  <div className="flex gap-1.5 text-[8px] mt-0.5">
                    <span className="text-slate-400">OI: {c.oi ? (c.oi/1000).toFixed(0) + 'K' : '0'}</span>
                    {c.iv && <span className="text-violet-300">IV: {c.iv.toFixed(1)}</span>}
                  </div>
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
                        }).filter(row => {
                          const maxOI = Math.max(row.ce_oi || 0, row.pe_oi || 0);
                          return maxOI >= minOI;
                        }).map(row => {
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
      </CardContent>
    </Card>
  );
}
