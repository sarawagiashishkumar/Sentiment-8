import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { GaugeCircle, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { SectorDrillDown } from "components/Shared/SectorDrillDown";

const API = "/api";
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

export function SectorsDashboard({ authHeaders, initialData }) {
  const [sectorMomentumData, setSectorMomentumData] = useState(initialData || null);
  const [sectorMomentumLoading, setSectorMomentumLoading] = useState(false);
  const [sectorMomentumError, setSectorMomentumError] = useState("");
  const [selectedSector, setSelectedSector] = useState(null);
  const intervalRef = useRef(null);

  const loadSectorMomentum = useCallback(async (forceRefresh = false, silent = false) => {
    if (!silent) {
      setSectorMomentumError("");
      setSectorMomentumLoading(true);
    }
    try {
      const response = await axios.get(`${API}/sector-momentum${forceRefresh ? "?force_refresh=true" : ""}`, { headers: authHeaders });
      setSectorMomentumData(response.data);
    } catch (error) {
      if (!silent) setSectorMomentumError(error?.response?.data?.detail || "Unable to load sector momentum data");
    } finally {
      if (!silent) setSectorMomentumLoading(false);
    }
  }, [authHeaders]);

  // Auto-fetch on mount
  useEffect(() => {
    if (!initialData) loadSectorMomentum(false);
  }, [initialData, loadSectorMomentum]);

  // Auto-refresh during market hours
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadSectorMomentum(true, true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadSectorMomentum]);

  return (
    <section className="space-y-6" data-testid="sectors-page">
      <Card className="result-card border-slate-800 bg-slate-950/70">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <CardTitle className="text-white">Sector Momentum Dashboard</CardTitle>
          <button
            type="button"
            onClick={() => loadSectorMomentum(true)}
            className="flex items-center gap-1.5 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 px-3 py-1.5 text-xs font-medium hover:bg-cyan-500/25 transition-all disabled:opacity-40"
            data-testid="sector-momentum-refresh-button"
            disabled={sectorMomentumLoading}
          >
            <RefreshCw size={14} className={sectorMomentumLoading ? "animate-spin" : ""} />
            {sectorMomentumLoading ? "Loading..." : "Refresh Data"}
          </button>
        </CardHeader>
        <CardContent>
          {sectorMomentumError ? <p className="text-sm text-rose-400" data-testid="sector-momentum-error">{sectorMomentumError}</p> : null}
          {!sectorMomentumData && !sectorMomentumLoading ? (
            <div className="flex flex-col items-center gap-3 py-8 text-slate-400" data-testid="sector-momentum-empty">
              <GaugeCircle size={40} className="opacity-40" />
              <p className="text-sm">Loading sector momentum data...</p>
            </div>
          ) : sectorMomentumLoading && !sectorMomentumData ? (
            <div className="flex items-center gap-2 py-8 text-slate-400" data-testid="sector-momentum-loading">
              <RefreshCw size={20} className="animate-spin" />
              <span>Fetching live sector momentum data... (may take ~30s on first load)</span>
            </div>
          ) : null}

          {sectorMomentumData ? (
            <>
              <div className="mb-4 flex flex-wrap gap-3 text-sm" data-testid="sector-momentum-summary">
                <span className="rounded bg-emerald-900/40 px-2 py-1 text-emerald-300 font-semibold">Bullish: {sectorMomentumData.summary?.bullish_sectors ?? 0}</span>
                <span className="rounded bg-rose-900/40 px-2 py-1 text-rose-300 font-semibold">Bearish: {sectorMomentumData.summary?.bearish_sectors ?? 0}</span>
                <span className="rounded bg-slate-700 px-2 py-1 text-slate-300 font-semibold">Neutral: {sectorMomentumData.summary?.neutral_sectors ?? 0}</span>
                <span className="rounded bg-cyan-900/40 px-2 py-1 text-cyan-300 font-semibold">Market: {sectorMomentumData.summary?.market_breadth ?? "--"}</span>
                <span className="rounded bg-slate-800 px-2 py-1 text-slate-400 text-xs font-mono">Avg Score: {sectorMomentumData.summary?.avg_momentum_score ?? "--"}</span>
                {sectorMomentumData.from_cache ? <span className="rounded bg-slate-800 px-2 py-1 text-slate-500 text-xs">cached</span> : null}
                <span className="rounded bg-slate-800 px-2 py-1 text-slate-500 text-xs font-mono">
                  {(sectorMomentumData.sectors || []).length}/{(sectorMomentumData.sectors || []).length} live
                </span>
                <span className="rounded bg-slate-800 px-2 py-1 text-slate-500 text-xs font-mono">
                  {sectorMomentumData.refreshed_at ? new Date(sectorMomentumData.refreshed_at).toLocaleTimeString("en-IN") : ""}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="sector-momentum-grid">
                {(sectorMomentumData.sectors || []).map((s) => (
                  <div key={s.sector} className={`rounded-lg border border-slate-700 bg-slate-900/60 p-3 cursor-pointer transition-all hover:border-cyan-500/50 ${
                    selectedSector === s.sector ? "ring-2 ring-cyan-400 border-cyan-500/50" : ""
                  }`} data-testid={`sector-card-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}
                  onClick={() => setSelectedSector(selectedSector === s.sector ? null : s.sector)}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="font-semibold text-slate-100 text-sm">{s.sector}</span>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold rounded px-2 py-0.5 ${
                          s.direction === "STRONG_BULL" ? "bg-emerald-900/60 text-emerald-300" :
                          s.direction === "BULL" ? "bg-green-900/60 text-green-400" :
                          s.direction === "NEUTRAL" ? "bg-yellow-900/60 text-yellow-300" :
                          s.direction === "BEAR" ? "bg-orange-900/60 text-orange-400" :
                          "bg-rose-900/60 text-rose-300"
                        }`} data-testid={`sector-direction-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>{s.direction_label}</span>
                        <span className="text-xs font-mono font-bold text-white bg-slate-700 rounded px-2 py-0.5" data-testid={`sector-score-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>{s.momentum_score}</span>
                      </div>
                    </div>
                    <div className="mb-2 h-1.5 w-full rounded-full bg-slate-700">
                      <div className={`h-1.5 rounded-full transition-all ${
                        s.direction === "STRONG_BULL" ? "bg-emerald-400" :
                        s.direction === "BULL" ? "bg-green-400" :
                        s.direction === "NEUTRAL" ? "bg-yellow-400" :
                        s.direction === "BEAR" ? "bg-orange-400" :
                        "bg-rose-500"
                      }`} style={{ width: `${s.momentum_score}%` }} />
                    </div>
                    <div className="grid grid-cols-3 gap-1 text-xs mb-2">
                      <div className="text-center">
                        <p className="text-slate-500">1W</p>
                        <p className={`font-mono font-semibold ${(s.return_1w ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`} data-testid={`sector-return-1w-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                          {s.return_1w != null ? `${s.return_1w >= 0 ? '+' : ''}${s.return_1w.toFixed(1)}%` : "--"}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-slate-500">1M</p>
                        <p className={`font-mono font-semibold ${(s.return_1m ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`} data-testid={`sector-return-1m-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                          {s.return_1m != null ? `${s.return_1m >= 0 ? '+' : ''}${s.return_1m.toFixed(1)}%` : "--"}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-slate-500">3M</p>
                        <p className={`font-mono font-semibold ${(s.return_3m ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`} data-testid={`sector-return-3m-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                          {s.return_3m != null ? `${s.return_3m >= 0 ? '+' : ''}${s.return_3m.toFixed(1)}%` : "--"}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      {s.rsi != null && (
                        <span className={`rounded px-1.5 py-0.5 ${s.rsi > 65 ? 'bg-orange-900/50 text-orange-300' : s.rsi < 35 ? 'bg-rose-900/50 text-rose-300' : 'bg-slate-800 text-slate-400'}`} data-testid={`sector-rsi-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>RSI {s.rsi.toFixed(0)}</span>
                      )}
                      {s.adx != null && (
                        <span className={`rounded px-1.5 py-0.5 ${s.adx > 25 ? 'bg-cyan-900/50 text-cyan-300' : 'bg-slate-800 text-slate-400'}`} data-testid={`sector-adx-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>ADX {s.adx.toFixed(0)} ({s.trend_strength})</span>
                      )}
                      <span className="rounded px-1.5 py-0.5 bg-slate-800 text-slate-500">{s.stocks_tracked} stocks</span>
                    </div>
                  </div>
                ))}
              </div>
              {selectedSector && (
                <SectorDrillDown
                  sector={selectedSector}
                  authHeaders={authHeaders}
                  onClose={() => setSelectedSector(null)}
                />
              )}
            </>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
