import { useState } from "react";
import axios from "axios";
import { ChevronRight, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function getMomentumColor(score) {
  if (score >= 70) return { bg: "bg-emerald-600/80", text: "text-white", border: "border-emerald-500/60" };
  if (score >= 57) return { bg: "bg-emerald-800/60", text: "text-emerald-200", border: "border-emerald-600/40" };
  if (score >= 43) return { bg: "bg-slate-700/70", text: "text-slate-200", border: "border-slate-600/50" };
  if (score >= 30) return { bg: "bg-rose-800/50", text: "text-rose-200", border: "border-rose-600/40" };
  return { bg: "bg-rose-700/70", text: "text-white", border: "border-rose-500/60" };
}

function getReturnColor(val) {
  if (val == null) return "text-slate-500";
  if (val >= 3) return "text-emerald-300";
  if (val >= 0) return "text-emerald-400/80";
  if (val >= -3) return "text-rose-400/80";
  return "text-rose-300";
}

export function SectorHeatmap({ authHeaders }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedSector, setExpandedSector] = useState(null);
  const [constituents, setConstituents] = useState({});
  const [constLoading, setConstLoading] = useState(null);

  const loadData = async () => {
    setError("");
    setLoading(true);
    try {
      const resp = await axios.get(`${API}/sector-momentum?force_refresh=false`, { headers: authHeaders });
      setData(resp.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load sector data");
    } finally {
      setLoading(false);
    }
  };

  const loadConstituents = async (sector) => {
    if (constituents[sector]) {
      setExpandedSector(expandedSector === sector ? null : sector);
      return;
    }
    setConstLoading(sector);
    setExpandedSector(sector);
    try {
      const resp = await axios.get(`${API}/market/sector-stocks?sector=${encodeURIComponent(sector)}`, { headers: authHeaders });
      setConstituents((prev) => ({ ...prev, [sector]: resp.data?.stocks || [] }));
    } catch {
      setConstituents((prev) => ({ ...prev, [sector]: [] }));
    } finally {
      setConstLoading(null);
    }
  };

  const sectors = data?.sectors || [];

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="sector-heatmap">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white text-sm">Sector Heatmap</CardTitle>
        <Button size="sm" onClick={loadData} disabled={loading} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="sector-heatmap-load">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          {loading ? "Loading..." : data ? "Refresh" : "Load Heatmap"}
        </Button>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-rose-400 mb-3" data-testid="sector-heatmap-error">{error}</p>}
        {!data && !loading && (
          <p className="text-sm text-slate-400 py-6 text-center">Click <strong>Load Heatmap</strong> to fetch live sector momentum.</p>
        )}
        {data && (
          <>
            <div className="mb-3 flex flex-wrap gap-2 text-xs">
              <span className="rounded bg-emerald-900/40 px-2 py-1 text-emerald-300 font-semibold">Bullish: {data.summary?.bullish_sectors ?? 0}</span>
              <span className="rounded bg-rose-900/40 px-2 py-1 text-rose-300 font-semibold">Bearish: {data.summary?.bearish_sectors ?? 0}</span>
              <span className="rounded bg-cyan-900/40 px-2 py-1 text-cyan-300 font-semibold">Market: {data.summary?.market_breadth ?? "—"}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" data-testid="sector-heatmap-grid">
              {sectors.map((s) => {
                const c = getMomentumColor(s.momentum_score);
                const isExpanded = expandedSector === s.sector;
                return (
                  <div key={s.sector}>
                    <button
                      data-testid={`heatmap-sector-${s.sector.toLowerCase().replace(/[^a-z]/g, "-")}`}
                      onClick={() => loadConstituents(s.sector)}
                      className={`w-full rounded-lg border ${c.border} ${c.bg} p-3 text-left transition-all hover:scale-[1.02] hover:brightness-110 cursor-pointer`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`font-semibold text-sm ${c.text}`}>{s.sector}</span>
                        <ChevronRight size={14} className={`${c.text} transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                      </div>
                      <div className={`text-2xl font-bold font-mono ${c.text}`}>{s.momentum_score}</div>
                      <div className="flex gap-2 mt-1 text-[10px]">
                        <span className={getReturnColor(s.return_1w)}>1W: {s.return_1w != null ? `${s.return_1w > 0 ? "+" : ""}${s.return_1w.toFixed(1)}%` : "—"}</span>
                        <span className={getReturnColor(s.return_1m)}>1M: {s.return_1m != null ? `${s.return_1m > 0 ? "+" : ""}${s.return_1m.toFixed(1)}%` : "—"}</span>
                      </div>
                      <div className="mt-1 text-[10px]">
                        {s.rsi != null && <span className={`${c.text} opacity-70`}>RSI {s.rsi.toFixed(0)}</span>}
                        {s.adx != null && <span className={`${c.text} opacity-70 ml-2`}>ADX {s.adx.toFixed(0)}</span>}
                      </div>
                    </button>
                    {isExpanded && (
                      <div className="mt-1 rounded-lg border border-slate-700 bg-slate-900/80 p-2 text-xs" data-testid={`sector-constituents-${s.sector.toLowerCase().replace(/[^a-z]/g, "-")}`}>
                        {constLoading === s.sector ? (
                          <p className="text-slate-400 py-2 text-center">Loading constituents...</p>
                        ) : (constituents[s.sector] || []).length === 0 ? (
                          <p className="text-slate-500 py-2 text-center">No constituent data available.</p>
                        ) : (
                          <div className="grid grid-cols-1 gap-1">
                            {(constituents[s.sector] || []).slice(0, 10).map((stock) => (
                              <div key={stock.symbol} className="flex items-center justify-between rounded px-2 py-1 hover:bg-slate-800/60">
                                <span className="font-mono text-slate-200">{stock.symbol}</span>
                                <span className={stock.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                  {stock.change_pct >= 0 ? "+" : ""}{stock.change_pct?.toFixed(2)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
