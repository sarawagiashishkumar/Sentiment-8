import { useCallback, useState } from "react";
import axios from "axios";
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RefreshCw, TrendingUp } from "lucide-react";

const API = "/api";

// Chart style constants — extracted to avoid re-render allocations
const CHART_TICK = { fontSize: 9, fill: "#94a3b8" };
const CHART_GRID_DASH = "3 3";
const CHART_GRID_STROKE = "#334155";
const TOOLTIP_STYLE = { background: "#1e293b", border: "1px solid #475569", borderRadius: 6, fontSize: 11 };
const TOOLTIP_LABEL = { color: "#94a3b8" };
const X_LABEL_DTE = { value: "Days to Expiry", position: "insideBottom", offset: -3, fontSize: 10, fill: "#64748b" };
const Y_LABEL_IV = { value: "IV %", angle: -90, position: "insideLeft", fontSize: 10, fill: "#64748b" };
const DOT_STYLE = { fill: "#a78bfa", r: 4 };

export function FNOIVAnalytics({ authHeaders }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [coneData, setConeData] = useState(null);
  const [termData, setTermData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectResult, setCollectResult] = useState(null);
  const [activeView, setActiveView] = useState("cone");

  const fetchIVData = useCallback(async () => {
    if (!symbol.trim()) return;
    setLoading(true);
    try {
      const [coneRes, termRes] = await Promise.all([
        axios.get(`${API}/fno/iv-cone/${symbol.trim().toUpperCase()}`, { headers: authHeaders }),
        axios.get(`${API}/fno/iv-term-structure/${symbol.trim().toUpperCase()}`, { headers: authHeaders }),
      ]);
      setConeData(coneRes.data);
      setTermData(termRes.data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [authHeaders, symbol]);

  const collectIVNow = useCallback(async () => {
    setCollecting(true);
    setCollectResult(null);
    try {
      const res = await axios.post(`${API}/fno/iv-collect-now`, {}, { headers: authHeaders });
      setCollectResult(res.data.results);
      // Refresh IV data after collection
      await fetchIVData();
    } catch { setCollectResult({ error: "Collection failed. Ensure Market Data API is connected." }); }
    finally { setCollecting(false); }
  }, [authHeaders, fetchIVData]);

  const hasConeData = coneData && coneData.data_points > 0;
  const hasTermData = termData && termData.data_points > 0;

  // Quick symbol presets
  const SYMBOL_PRESETS = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK"];

  return (
    <div className="space-y-3" data-testid="fno-iv-analytics">
      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Quick presets */}
        {SYMBOL_PRESETS.map((s) => (
          <button
            key={s}
            onClick={() => { setSymbol(s); }}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              symbol === s ? "bg-violet-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
            }`}
            data-testid={`iv-preset-${s.toLowerCase()}`}
          >{s}</button>
        ))}
        <Input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Custom symbol..."
          className="w-32 border-slate-700 bg-slate-800 text-slate-100 text-xs h-8"
          data-testid="iv-symbol-input"
        />
        <Button
          onClick={fetchIVData} disabled={loading}
          className="h-8 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3"
          data-testid="iv-fetch-btn"
        >
          <RefreshCw size={13} className={loading ? "animate-spin mr-1" : "mr-1"} />
          {loading ? "Loading..." : "Fetch IV"}
        </Button>
        <Button
          onClick={collectIVNow} disabled={collecting}
          className="h-8 bg-violet-600 text-white hover:bg-violet-500 text-xs px-3"
          data-testid="iv-collect-now-btn"
        >
          <TrendingUp size={13} className="mr-1" />
          {collecting ? "Collecting..." : "Collect IV Now"}
        </Button>
        <div className="flex rounded-md border border-slate-700 overflow-hidden ml-2">
          {[
            { key: "cone", label: "IV Cone" },
            { key: "term", label: "Term Structure" },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveView(t.key)}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                activeView === t.key
                  ? "bg-violet-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-slate-200"
              }`}
              data-testid={`iv-tab-${t.key}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Data collection status */}
      {coneData && coneData.data_points < 30 && coneData.data_points > 0 && (
        <div className="rounded-lg border border-amber-600/30 bg-amber-950/20 p-2.5 text-xs text-amber-300" data-testid="iv-data-status">
          Collecting IV data: {coneData.data_points}/30 days minimum. Percentile bands become more reliable with 30+ days of history. Data accumulates as signals are generated.
        </div>
      )}

      {/* Collect IV result */}
      {collectResult && !collectResult.error && (
        <div className="flex flex-wrap gap-2" data-testid="iv-collect-result">
          {Object.entries(collectResult).map(([sym, r]) => (
            <span key={sym} className={`rounded px-2 py-1 text-[10px] font-mono ${r.captured ? "bg-emerald-900/40 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>
              {sym}: {r.captured ? `IV ${r.atm_iv}% (${r.term_expiries} expiries)` : r.reason}
            </span>
          ))}
        </div>
      )}
      {collectResult?.error && (
        <p className="text-xs text-rose-400">{collectResult.error}</p>
      )}

      {/* IV Cone View */}
      {activeView === "cone" && (
        <div data-testid="iv-cone-panel">
          {!coneData ? (
            <EmptyBox message="Enter a symbol and click Fetch IV to view the IV Cone." />
          ) : !hasConeData ? (
            <EmptyBox message={coneData.message || "No IV history data yet."} />
          ) : (
            <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-slate-400">{coneData.symbol} IV Cone ({coneData.data_points} data points)</span>
                {coneData.current_iv && (
                  <span className="text-xs font-bold text-cyan-300">Current IV: {coneData.current_iv}%</span>
                )}
              </div>
              {/* Band stats */}
              {coneData.bands && (
                <div className="flex flex-wrap gap-2 mb-3">
                  {[
                    { k: "p90", label: "90th", color: "text-rose-300" },
                    { k: "p75", label: "75th", color: "text-amber-300" },
                    { k: "p50", label: "50th", color: "text-slate-300" },
                    { k: "p25", label: "25th", color: "text-emerald-300" },
                    { k: "p10", label: "10th", color: "text-teal-300" },
                  ].map((b) => (
                    <span key={b.k} className={`rounded bg-slate-800/70 px-1.5 py-0.5 text-[10px] ${b.color}`}>
                      {b.label}: {coneData.bands[b.k]}%
                    </span>
                  ))}
                </div>
              )}
              {/* Chart */}
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={coneData.points}>
                  <CartesianGrid strokeDasharray={CHART_GRID_DASH} stroke={CHART_GRID_STROKE} />
                  <XAxis dataKey="date" tick={CHART_TICK} interval="preserveStartEnd" />
                  <YAxis tick={CHART_TICK} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} />
                  <Area type="monotone" dataKey="iv" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.15} strokeWidth={1.5} name="ATM IV %" />
                  {/* Band reference lines */}
                  {coneData.bands && (
                    <>
                      <Area type="monotone" dataKey={() => coneData.bands.p90} stroke="#ef444480" fill="none" strokeDasharray="4 4" strokeWidth={1} name="90th" />
                      <Area type="monotone" dataKey={() => coneData.bands.p50} stroke="#94a3b880" fill="none" strokeDasharray="4 4" strokeWidth={1} name="50th" />
                      <Area type="monotone" dataKey={() => coneData.bands.p10} stroke="#14b8a680" fill="none" strokeDasharray="4 4" strokeWidth={1} name="10th" />
                    </>
                  )}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* IV Term Structure View */}
      {activeView === "term" && (
        <div data-testid="iv-term-panel">
          {!termData ? (
            <EmptyBox message="Enter a symbol and click Fetch IV to view the Term Structure." />
          ) : !hasTermData ? (
            <EmptyBox message={termData.message || "No term structure data yet."} />
          ) : (
            <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-3">
              <span className="text-xs text-slate-400 block mb-2">
                {termData.symbol} IV Term Structure (captured: {termData.captured_at})
              </span>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={termData.term_points}>
                  <CartesianGrid strokeDasharray={CHART_GRID_DASH} stroke={CHART_GRID_STROKE} />
                  <XAxis dataKey="dte" tick={CHART_TICK} label={X_LABEL_DTE} />
                  <YAxis tick={CHART_TICK} label={Y_LABEL_IV} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(val, name) => [`${val}%`, name]} />
                  <Line type="monotone" dataKey="iv" stroke="#a78bfa" strokeWidth={2} dot={DOT_STYLE} name="IV" />
                </LineChart>
              </ResponsiveContainer>
              {/* Term points table */}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {termData.term_points.map((pt) => (
                  <span key={`${pt.expiry}-${pt.dte}`} className="rounded bg-slate-800/70 px-1.5 py-0.5 text-[10px] text-slate-300">
                    {pt.expiry} ({pt.dte}d): <span className="text-violet-300 font-semibold">{pt.iv}%</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EmptyBox({ message }) {
  return (
    <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-6 text-center text-slate-500 text-sm">
      <TrendingUp size={24} className="mx-auto mb-2 opacity-50" />
      {message}
    </div>
  );
}
