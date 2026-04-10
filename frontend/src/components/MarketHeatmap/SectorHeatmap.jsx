import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { ChevronRight, RefreshCw, TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  const mins = h * 60 + m;
  return mins >= 555 && mins <= 930; // 9:15 to 15:30
}

function getMomentumColor(score) {
  if (score >= 65) return "border-emerald-500/50 bg-emerald-900/40 text-emerald-100";
  if (score >= 55) return "border-emerald-600/30 bg-emerald-950/40 text-emerald-200";
  if (score >= 45) return "border-slate-600/40 bg-slate-800/50 text-slate-200";
  if (score >= 35) return "border-rose-600/30 bg-rose-950/40 text-rose-200";
  return "border-rose-500/50 bg-rose-900/40 text-rose-100";
}

function getChangeColor(pct) {
  if (pct >= 2) return "border-emerald-500/50 bg-emerald-900/50 text-emerald-100";
  if (pct >= 0.5) return "border-emerald-600/30 bg-emerald-950/40 text-emerald-200";
  if (pct >= -0.5) return "border-slate-600/40 bg-slate-800/50 text-slate-200";
  if (pct >= -2) return "border-rose-600/30 bg-rose-950/40 text-rose-200";
  return "border-rose-500/50 bg-rose-900/40 text-rose-100";
}

function getReturnColor(val) {
  if (val == null) return "text-slate-500";
  return val >= 0 ? "text-emerald-400" : "text-rose-400";
}

export function SectorHeatmap({ authHeaders, onFetchError }) {
  const [sectorData, setSectorData] = useState(null);
  const [industryData, setIndustryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedSector, setExpandedSector] = useState(null);
  const [constituents, setConstituents] = useState({});
  const [constLoading, setConstLoading] = useState(null);
  const intervalRef = useRef(null);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [sectorResp, industryResp] = await Promise.all([
        axios.get(`${API}/sector-momentum?force_refresh=false`, { headers: authHeaders }),
        axios.get(`${API}/market/industry-sectors`, { headers: authHeaders }).catch(() => null),
      ]);
      setSectorData(sectorResp.data);
      if (industryResp?.data) setIndustryData(industryResp.data);
    } catch (e) {
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  }, [authHeaders, onFetchError]);

  // Auto-fetch on mount
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh during market hours
  useEffect(() => {
    const startPolling = () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(() => {
        if (isMarketHours()) loadData(true);
      }, REFRESH_INTERVAL);
    };
    startPolling();
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  const loadConstituents = async (sector) => {
    if (constituents[sector]) {
      setExpandedSector(expandedSector === sector ? null : sector);
      return;
    }
    setConstLoading(sector);
    setExpandedSector(sector);
    try {
      const resp = await axios.get(`${API}/market/sector-stocks?sector=${encodeURIComponent(sector)}`, { headers: authHeaders });
      setConstituents(prev => ({ ...prev, [sector]: resp.data?.stocks || [] }));
    } catch {
      setConstituents(prev => ({ ...prev, [sector]: [] }));
    } finally {
      setConstLoading(null);
    }
  };

  const sectors = sectorData?.sectors || [];
  const industrySectors = industryData?.sectors || [];

  return (
    <div className="space-y-4">
      <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="sector-heatmap">
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
          <CardTitle className="text-white text-base">Market Sector Heatmap</CardTitle>
          <button onClick={() => loadData()} disabled={loading} className="flex items-center gap-1.5 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 px-3 py-1.5 text-xs font-medium hover:bg-cyan-500/25 transition-all disabled:opacity-40" data-testid="sector-heatmap-refresh">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            {loading ? "Loading..." : "Refresh"}
          </button>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* NSE Index Sectors */}
          {sectors.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 mb-2 tracking-wide" data-testid="nse-sectors-heading">
                NSE Index Sectors ({sectors.length})
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2" data-testid="sector-heatmap-grid">
                {sectors.map((s) => {
                  const colorCls = getMomentumColor(s.momentum_score);
                  const isExpanded = expandedSector === s.sector;
                  return (
                    <div key={s.sector}>
                      <button
                        data-testid={`heatmap-sector-${s.sector.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
                        onClick={() => loadConstituents(s.sector)}
                        className={`w-full rounded-lg border ${colorCls} p-2.5 text-left transition-all hover:brightness-110 hover:scale-[1.02] cursor-pointer`}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="font-semibold text-xs truncate pr-1">{s.sector}</span>
                          <ChevronRight size={11} className={`shrink-0 opacity-60 transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                        </div>
                        <div className="text-xl font-bold font-mono">{s.momentum_score}</div>
                        <div className="text-[10px] mt-0.5 opacity-80">
                          <span className={getReturnColor(s.return_1w)}>1W: {s.return_1w != null ? `${s.return_1w >= 0 ? "+" : ""}${s.return_1w.toFixed(1)}%` : "--"}</span>
                        </div>
                      </button>
                      {isExpanded && (
                        <div className="mt-1 rounded-lg border border-slate-700 bg-slate-900/80 p-2 text-xs" data-testid={`sector-constituents-${s.sector.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}>
                          {constLoading === s.sector ? (
                            <p className="text-slate-400 py-2 text-center">Loading...</p>
                          ) : (constituents[s.sector] || []).length === 0 ? (
                            <p className="text-slate-500 py-2 text-center">No constituent data.</p>
                          ) : (
                            <div className="grid grid-cols-1 gap-0.5">
                              {(constituents[s.sector] || []).slice(0, 10).map((stock) => (
                                <div key={stock.symbol} className="flex items-center justify-between rounded px-2 py-0.5 hover:bg-slate-800/60">
                                  <span className="font-mono text-slate-200 text-[10px]">{stock.symbol}</span>
                                  <span className={`text-[10px] font-mono ${stock.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
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

              {/* Summary badges */}
              {sectorData?.summary && (
                <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                  <span className="rounded bg-emerald-900/40 px-2 py-0.5 text-emerald-300 font-semibold">Bullish: {sectorData.summary.bullish_sectors ?? 0}</span>
                  <span className="rounded bg-rose-900/40 px-2 py-0.5 text-rose-300 font-semibold">Bearish: {sectorData.summary.bearish_sectors ?? 0}</span>
                  <span className="rounded bg-slate-700 px-2 py-0.5 text-slate-300 font-semibold">Neutral: {sectorData.summary.neutral_sectors ?? 0}</span>
                  <span className="rounded bg-cyan-900/40 px-2 py-0.5 text-cyan-300 font-semibold">Market: {sectorData.summary.market_breadth ?? "--"}</span>
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-400 font-mono">Avg: {sectorData.summary.avg_momentum_score ?? "--"}</span>
                  {sectorData.from_cache && <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-500">cached</span>}
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-500">{sectors.length}/{sectors.length} live</span>
                  {sectorData.refreshed_at && (
                    <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-500 font-mono">
                      {new Date(sectorData.refreshed_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Industry Sectors */}
          {industrySectors.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 mb-2 tracking-wide" data-testid="industry-sectors-heading">
                Industry Sectors ({industrySectors.length})
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2" data-testid="industry-sectors-grid">
                {industrySectors.map((s) => {
                  const colorCls = getChangeColor(s.avg_change_pct);
                  return (
                    <div
                      key={s.sector}
                      data-testid={`industry-sector-${s.sector.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
                      className={`rounded-lg border ${colorCls} p-2.5 transition-all hover:brightness-110`}
                    >
                      <div className="font-semibold text-xs truncate mb-0.5">{s.sector}</div>
                      <div className={`text-lg font-bold font-mono ${s.avg_change_pct >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                        {s.avg_change_pct >= 0 ? "+" : ""}{s.avg_change_pct?.toFixed(2)}%
                      </div>
                      <div className="flex gap-2 text-[9px] mt-0.5 opacity-70">
                        <span>{s.stock_count} stocks</span>
                        <span className="text-emerald-400">{s.gainers}<TrendingUp size={8} className="inline ml-0.5" /></span>
                        <span className="text-rose-400">{s.losers}<TrendingDown size={8} className="inline ml-0.5" /></span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!sectorData && !loading && (
            <p className="text-sm text-slate-400 py-6 text-center">Loading sector data...</p>
          )}
          {loading && !sectorData && (
            <div className="flex items-center justify-center gap-2 py-8 text-slate-400">
              <RefreshCw size={16} className="animate-spin" />
              <span className="text-sm">Loading sector data...</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
