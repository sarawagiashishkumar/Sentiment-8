import { useCallback, useState } from "react";
import axios from "axios";
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RefreshCw, TrendingUp } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function FNOIVAnalytics({ authHeaders }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [coneData, setConeData] = useState(null);
  const [termData, setTermData] = useState(null);
  const [loading, setLoading] = useState(false);
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

  const hasConeData = coneData && coneData.data_points > 0;
  const hasTermData = termData && termData.data_points > 0;

  return (
    <div className="space-y-3" data-testid="fno-iv-analytics">
      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        <Input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Symbol (e.g. NIFTY, RELIANCE)"
          className="w-44 border-slate-700 bg-slate-800 text-slate-100 text-xs h-8"
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
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #475569", borderRadius: 6, fontSize: 11 }}
                    labelStyle={{ color: "#94a3b8" }}
                  />
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
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="dte" tick={{ fontSize: 9, fill: "#94a3b8" }} label={{ value: "Days to Expiry", position: "insideBottom", offset: -3, fontSize: 10, fill: "#64748b" }} />
                  <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} label={{ value: "IV %", angle: -90, position: "insideLeft", fontSize: 10, fill: "#64748b" }} />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #475569", borderRadius: 6, fontSize: 11 }}
                    formatter={(val, name) => [`${val}%`, name]}
                  />
                  <Line type="monotone" dataKey="iv" stroke="#a78bfa" strokeWidth={2} dot={{ fill: "#a78bfa", r: 4 }} name="IV" />
                </LineChart>
              </ResponsiveContainer>
              {/* Term points table */}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {termData.term_points.map((pt, i) => (
                  <span key={i} className="rounded bg-slate-800/70 px-1.5 py-0.5 text-[10px] text-slate-300">
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
