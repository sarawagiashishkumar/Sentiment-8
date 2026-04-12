import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import axios from "axios";
import { HeatmapSkeleton } from "@/components/Shared/Skeletons";
import { OptionsControls } from "./OptionsControls";
import { OptionsTreemapView } from "./OptionsTreemapView";
import { OptionsChainView } from "./OptionsChainView";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const REFRESH_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

export function OptionsHeatmap({ authHeaders, onFetchError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeSymbol, setActiveSymbol] = useState("nifty");
  const [selectedExpiry, setSelectedExpiry] = useState("");
  const [oiTypeFilter, setOiTypeFilter] = useState("all");
  const [viewMode, setViewMode] = useState("treemap");
  const [minOI, setMinOI] = useState(0);
  const intervalRef = useRef(null);
  const symbolRef = useRef(activeSymbol);
  const expiryRef = useRef(selectedExpiry);

  const loadData = useCallback(async (symbol, expiryParam = "", silent = false) => {
    if (!silent) setLoading(true);
    try {
      let url = `${API}/market/options-heatmap?filter=${symbol}`;
      if (expiryParam) url += `&expiry=${encodeURIComponent(expiryParam)}`;
      const resp = await axios.get(url, { headers: authHeaders });
      setData(resp.data);
      if (!resp.data.kite_live && onFetchError) onFetchError();
    } catch (err) {
      console.error("Options heatmap fetch error:", err?.message);
      if (onFetchError) onFetchError();
    } finally {
      setLoading(false);
    }
  }, [authHeaders, onFetchError]);

  useEffect(() => { loadData(activeSymbol, selectedExpiry); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    symbolRef.current = activeSymbol;
    setSelectedExpiry("");
    loadData(activeSymbol, "");
  }, [activeSymbol, loadData]);

  useEffect(() => {
    if (selectedExpiry) loadData(activeSymbol, selectedExpiry);
  }, [selectedExpiry, activeSymbol, loadData]);

  expiryRef.current = selectedExpiry;

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) loadData(symbolRef.current, expiryRef.current, true);
    }, REFRESH_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  const chains = data?.chains || [];
  const availableExpiries = chains.length > 0 ? (chains[0].available_expiries || []) : [];

  // Build flat contract list for treemap
  const allContracts = useMemo(() => {
    const result = [];
    chains.forEach(item => {
      (item.strikes || []).forEach(row => {
        if (oiTypeFilter === "all" || oiTypeFilter === "ce") {
          if (row.ce_ltp != null) {
            const oi = row.ce_oi || 0;
            if (oi >= minOI) {
              result.push({
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
              result.push({
                ts: row.pe_ts || `${item.symbol}${row.strike}PE`,
                type: "PE", strike: row.strike, ltp: row.pe_ltp, oi, iv: row.pe_iv,
                symbol: item.symbol, spot: item.spot,
              });
            }
          }
        }
      });
    });
    result.sort((a, b) => (b.oi || 0) - (a.oi || 0));
    return result;
  }, [chains, oiTypeFilter, minOI]);

  if (loading && !data) return <HeatmapSkeleton />;

  return (
    <div className="space-y-3" data-testid="options-heatmap">
      <OptionsControls
        activeSymbol={activeSymbol} setActiveSymbol={setActiveSymbol}
        oiTypeFilter={oiTypeFilter} setOiTypeFilter={setOiTypeFilter}
        selectedExpiry={selectedExpiry} setSelectedExpiry={setSelectedExpiry}
        availableExpiries={availableExpiries}
        minOI={minOI} setMinOI={setMinOI}
        viewMode={viewMode} setViewMode={setViewMode}
        refreshIntervalMs={REFRESH_INTERVAL}
        onManualRefresh={() => loadData(activeSymbol, selectedExpiry)}
      />

      <div className="text-right">
        <span className="text-xs text-slate-500 font-mono" data-testid="options-contract-count">{allContracts.length} contracts</span>
      </div>

      {data?.warning && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="options-warning">{data.warning}</div>
      )}

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

      {data && viewMode === "treemap" && allContracts.length > 0 && (
        <OptionsTreemapView contracts={allContracts} />
      )}

      {data && viewMode === "chain" && chains.length > 0 && (
        <OptionsChainView chains={chains} oiTypeFilter={oiTypeFilter} minOI={minOI} />
      )}

      {data && allContracts.length === 0 && chains.length === 0 && !loading && (
        <p className="text-sm text-slate-400 text-center py-4" data-testid="options-no-data">No options data. Ensure Market Data API is connected.</p>
      )}
    </div>
  );
}
