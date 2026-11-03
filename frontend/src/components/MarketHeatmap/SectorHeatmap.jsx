import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { TrendingUp, TrendingDown } from "lucide-react";
import { SectorDrillDown } from "@/components/Shared/SectorDrillDown";
import { RefreshCountdown } from "@/components/Shared/RefreshCountdown";

const API = "/api";
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

/** Get gradient background style based on value intensity */
function getGradientStyle(value) {
  const absVal = Math.abs(value);
  // Opacity scales from 0.15 (near zero) to 0.95 (extreme values)
  const intensity = Math.min(absVal / 6, 1);
  const opacity = 0.15 + intensity * 0.8;
  if (value >= 0) {
    return { backgroundColor: `rgba(16, 185, 129, ${opacity})`, borderColor: `rgba(16, 185, 129, ${0.2 + intensity * 0.5})` };
  }
  return { backgroundColor: `rgba(239, 68, 68, ${opacity})`, borderColor: `rgba(239, 68, 68, ${0.2 + intensity * 0.5})` };
}

export function SectorHeatmap({ authHeaders, onFetchError }) {
  const [sectorData, setSectorData] = useState(null);
  const [industryData, setIndustryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedSector, setSelectedSector] = useState(null);
  const intervalRef = useRef(null);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [sectorResp, industryResp] = await Promise.all([
        axios.get(`${API}/sector-momentum?force_refresh=true`, { headers: authHeaders }),
        axios.get(`${API}/market/industry-sectors`, { headers: authHeaders }).catch(() => null),
      ]);
      setSectorData(sectorResp.data);
      if (industryResp?.data) setIndustryData(industryResp.data);
    } catch {
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  }, [authHeaders, onFetchError]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadData(true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  const sectors = [...(sectorData?.sectors || [])].sort((a, b) => (b.momentum_score || 0) - (a.momentum_score || 0));
  const industrySectors = [...(industryData?.sectors || [])].sort((a, b) => (b.avg_change_pct || 0) - (a.avg_change_pct || 0));

  if (loading && !sectorData) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-8">
        <p className="text-sm text-slate-400 text-center animate-pulse">Loading sector data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="sector-heatmap">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white" data-testid="sector-heatmap-title">Market Sector Heatmap</h2>
        <RefreshCountdown intervalMs={REFRESH_INTERVAL} isActive={true} onManualRefresh={() => loadData()} />
      </div>

      {/* NSE Index Sectors */}
      {sectors.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-400 mb-3 tracking-wide" data-testid="nse-sectors-heading">
            NSE Index Sectors ({sectors.length})
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2" data-testid="sector-heatmap-grid">
            {sectors.map((s) => {
              const score = s.momentum_score || 0;
              const tileStyle = getGradientStyle(score > 50 ? (score - 50) / 10 : -(50 - score) / 10);
              return (
                <div
                  key={s.sector}
                  data-testid={`heatmap-sector-${s.sector.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
                  className={`rounded-lg border p-3 transition-all hover:brightness-110 hover:scale-[1.02] cursor-pointer ${
                    selectedSector === s.sector ? "ring-2 ring-cyan-400" : ""
                  }`}
                  style={tileStyle}
                  onClick={() => setSelectedSector(selectedSector === s.sector ? null : s.sector)}
                >
                  <div className="font-semibold text-xs text-white/90 truncate mb-1">{s.sector}</div>
                  <div className="text-2xl font-bold font-mono text-white">{Math.round(score)}</div>
                  <div className="text-[10px] mt-1 text-white/70">
                    1W: {s.return_1w != null ? `${s.return_1w >= 0 ? "+" : ""}${s.return_1w.toFixed(1)}%` : "--"}
                  </div>
                </div>
              );
            })}
          </div>
          {selectedSector && sectors.some(s => s.sector === selectedSector) && (
            <SectorDrillDown
              sector={selectedSector}
              authHeaders={authHeaders}
              onClose={() => setSelectedSector(null)}
            />
          )}
        </div>
      )}

      {/* Industry Sectors */}
      {industrySectors.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-400 mb-3 tracking-wide" data-testid="industry-sectors-heading">
            Industry Sectors ({industrySectors.length})
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2" data-testid="industry-sectors-grid">
            {industrySectors.map((s) => {
              const tileStyle = getGradientStyle(s.avg_change_pct || 0);
              return (
                <div
                  key={s.sector}
                  data-testid={`industry-sector-${s.sector.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
                  className={`rounded-lg border p-3 transition-all hover:brightness-110 cursor-pointer ${
                    selectedSector === s.sector ? "ring-2 ring-cyan-400" : ""
                  }`}
                  style={tileStyle}
                  onClick={() => setSelectedSector(selectedSector === s.sector ? null : s.sector)}
                >
                  <div className="font-semibold text-xs text-white/90 truncate mb-1">{s.sector}</div>
                  <div className={`text-xl font-bold font-mono text-white`}>
                    {s.avg_change_pct >= 0 ? "+" : ""}{s.avg_change_pct?.toFixed(2)}%
                  </div>
                  <div className="flex items-center gap-2 text-[9px] mt-1 text-white/60">
                    <span>{s.stock_count} stocks</span>
                    <span className="text-emerald-300">{s.gainers}<TrendingUp size={8} className="inline ml-0.5" /></span>
                    <span className="text-rose-300">{s.losers}<TrendingDown size={8} className="inline ml-0.5" /></span>
                  </div>
                </div>
              );
            })}
          </div>
          {selectedSector && industrySectors.some(s => s.sector === selectedSector) && (
            <SectorDrillDown
              sector={selectedSector}
              authHeaders={authHeaders}
              onClose={() => setSelectedSector(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
