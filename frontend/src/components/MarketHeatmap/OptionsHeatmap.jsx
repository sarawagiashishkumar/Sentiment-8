import { useState } from "react";
import axios from "axios";
import { Layers, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FILTER_PRESETS = [
  { id: "nifty", label: "NIFTY Options" },
  { id: "banknifty", label: "BANKNIFTY Options" },
  { id: "stocks", label: "Stock Options" },
];

function getOIColor(buildup) {
  if (buildup === "LONG_BUILDUP") return "bg-emerald-700/70 text-emerald-100 border-emerald-500/50";
  if (buildup === "SHORT_COVERING") return "bg-emerald-800/50 text-emerald-200 border-emerald-600/30";
  if (buildup === "SHORT_BUILDUP") return "bg-rose-700/70 text-rose-100 border-rose-500/50";
  if (buildup === "LONG_UNWINDING") return "bg-rose-800/50 text-rose-200 border-rose-600/30";
  return "bg-slate-800/60 text-slate-300 border-slate-600/40";
}

export function OptionsHeatmap({ authHeaders }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeFilter, setActiveFilter] = useState("nifty");

  const loadData = async () => {
    setError("");
    setLoading(true);
    try {
      const resp = await axios.get(`${API}/market/options-heatmap?filter=${activeFilter}`, { headers: authHeaders });
      setData(resp.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load options heatmap");
    } finally {
      setLoading(false);
    }
  };

  const chains = data?.chains || [];

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="options-heatmap">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 flex-wrap">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          <Layers size={14} />
          Options Heatmap
        </CardTitle>
        <Button size="sm" onClick={loadData} disabled={loading} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="options-heatmap-load">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          {loading ? "Loading..." : data ? "Refresh" : "Load Options"}
        </Button>
      </CardHeader>
      <CardContent>
        <div className="mb-3 flex flex-wrap gap-1" data-testid="options-heatmap-filters">
          {FILTER_PRESETS.map((f) => (
            <button
              key={f.id}
              data-testid={`options-filter-${f.id}`}
              onClick={() => setActiveFilter(f.id)}
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

        {error && <p className="text-sm text-rose-400 mb-3" data-testid="options-heatmap-error">{error}</p>}
        {!data && !loading && (
          <p className="text-sm text-slate-400 py-6 text-center">Select a filter and click <strong>Load Options</strong> for live OI/IV data.</p>
        )}
        {data && (
          <>
            {data.summary && (
              <div className="mb-3 flex flex-wrap gap-2 text-xs">
                {data.summary.max_pain != null && <span className="rounded bg-amber-900/40 px-2 py-1 text-amber-300">Max Pain: {data.summary.max_pain}</span>}
                {data.summary.pcr != null && <span className="rounded bg-slate-800 px-2 py-1 text-slate-300">PCR: {data.summary.pcr}</span>}
                {data.summary.iv_rank != null && <span className="rounded bg-violet-900/40 px-2 py-1 text-violet-300">IV Rank: {data.summary.iv_rank}%</span>}
                {data.summary.oi_buildup && <span className={`rounded px-2 py-1 font-semibold ${getOIColor(data.summary.oi_buildup).replace("border-", "")}`}>{data.summary.oi_buildup.replace(/_/g, " ")}</span>}
              </div>
            )}
            <div className="space-y-2" data-testid="options-heatmap-grid">
              {chains.map((item) => (
                <div key={item.symbol} className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono font-semibold text-sm text-slate-100">{item.symbol}</span>
                    <span className="text-xs text-slate-400">Spot: {item.spot?.toFixed(2)}</span>
                  </div>
                  {item.strikes?.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-[10px]">
                        <thead>
                          <tr className="text-slate-500">
                            <th className="px-2 py-1 text-right">CE OI</th>
                            <th className="px-2 py-1 text-right">CE IV</th>
                            <th className="px-2 py-1 text-right">CE LTP</th>
                            <th className="px-2 py-1 text-center font-bold text-cyan-400">Strike</th>
                            <th className="px-2 py-1 text-left">PE LTP</th>
                            <th className="px-2 py-1 text-left">PE IV</th>
                            <th className="px-2 py-1 text-left">PE OI</th>
                          </tr>
                        </thead>
                        <tbody>
                          {item.strikes.map((row) => {
                            const isATM = Math.abs(row.strike - item.spot) <= (item.step || 50);
                            return (
                              <tr key={row.strike} className={isATM ? "bg-cyan-900/20" : "hover:bg-slate-800/40"}>
                                <td className="px-2 py-0.5 text-right font-mono text-emerald-400">{row.ce_oi ? (row.ce_oi / 1000).toFixed(0) + "K" : "—"}</td>
                                <td className="px-2 py-0.5 text-right font-mono text-violet-300">{row.ce_iv?.toFixed(1) || "—"}</td>
                                <td className="px-2 py-0.5 text-right font-mono text-slate-200">{row.ce_ltp?.toFixed(2) || "—"}</td>
                                <td className={`px-2 py-0.5 text-center font-mono font-bold ${isATM ? "text-cyan-300" : "text-slate-400"}`}>{row.strike}</td>
                                <td className="px-2 py-0.5 text-left font-mono text-slate-200">{row.pe_ltp?.toFixed(2) || "—"}</td>
                                <td className="px-2 py-0.5 text-left font-mono text-violet-300">{row.pe_iv?.toFixed(1) || "—"}</td>
                                <td className="px-2 py-0.5 text-left font-mono text-rose-400">{row.pe_oi ? (row.pe_oi / 1000).toFixed(0) + "K" : "—"}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 text-center py-2">No option chain data available.</p>
                  )}
                </div>
              ))}
              {chains.length === 0 && <p className="text-sm text-slate-400 text-center py-4">No options data available. Ensure Kite is connected.</p>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
