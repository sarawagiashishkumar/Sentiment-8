import { useState } from "react";
import axios from "axios";
import { Filter, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FILTER_PRESETS = [
  { id: "all", label: "All Stocks" },
  { id: "nifty50", label: "Nifty 50" },
  { id: "banknifty", label: "BankNifty" },
  { id: "plus5", label: "+5% Gainers" },
  { id: "plus3", label: "+3% Gainers" },
  { id: "minus3", label: "-3% Losers" },
  { id: "minus5", label: "-5% Losers" },
  { id: "fno", label: "F&O Universe" },
];

function getChangeColor(pct) {
  if (pct >= 5) return "bg-emerald-600 text-white";
  if (pct >= 3) return "bg-emerald-700/80 text-emerald-100";
  if (pct >= 1) return "bg-emerald-800/60 text-emerald-200";
  if (pct >= 0) return "bg-emerald-900/40 text-emerald-300";
  if (pct >= -1) return "bg-rose-900/40 text-rose-300";
  if (pct >= -3) return "bg-rose-800/60 text-rose-200";
  if (pct >= -5) return "bg-rose-700/80 text-rose-100";
  return "bg-rose-600 text-white";
}

function getCellSize(pct) {
  const abs = Math.abs(pct || 0);
  if (abs >= 5) return "min-h-[72px]";
  if (abs >= 3) return "min-h-[60px]";
  return "min-h-[48px]";
}

export function StocksHeatmap({ authHeaders }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeFilter, setActiveFilter] = useState("fno");

  const loadData = async () => {
    setError("");
    setLoading(true);
    try {
      const resp = await axios.get(`${API}/market/stock-heatmap?filter=${activeFilter}`, { headers: authHeaders });
      setData(resp.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load stock heatmap");
    } finally {
      setLoading(false);
    }
  };

  const stocks = data?.stocks || [];
  const gainers = stocks.filter((s) => s.change_pct > 0).length;
  const losers = stocks.filter((s) => s.change_pct < 0).length;

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="stocks-heatmap">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 flex-wrap">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          <Filter size={14} />
          Stocks Heatmap
        </CardTitle>
        <Button size="sm" onClick={loadData} disabled={loading} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="stocks-heatmap-load">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          {loading ? "Loading..." : data ? "Refresh" : "Load Heatmap"}
        </Button>
      </CardHeader>
      <CardContent>
        <div className="mb-3 flex flex-wrap gap-1" data-testid="stocks-heatmap-filters">
          {FILTER_PRESETS.map((f) => (
            <button
              key={f.id}
              data-testid={`stocks-filter-${f.id}`}
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

        {error && <p className="text-sm text-rose-400 mb-3" data-testid="stocks-heatmap-error">{error}</p>}
        {data && !data.kite_live && (
          <div className="mb-3 rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs text-amber-300" data-testid="stocks-heatmap-no-live">
            No live Kite data available. All prices shown as 0. Ensure Kite is connected in Admin panel.
          </div>
        )}
        {!data && !loading && (
          <p className="text-sm text-slate-400 py-6 text-center">Select a filter and click <strong>Load Heatmap</strong>.</p>
        )}
        {data && (
          <>
            <div className="mb-3 flex gap-3 text-xs">
              <span className="text-emerald-400 font-semibold">{gainers} Gainers</span>
              <span className="text-rose-400 font-semibold">{losers} Losers</span>
              <span className="text-slate-400">{stocks.length} Total</span>
            </div>
            <div className="flex flex-wrap gap-1" data-testid="stocks-heatmap-grid">
              {stocks.map((s) => (
                <div
                  key={s.symbol}
                  data-testid={`stock-tile-${s.symbol.toLowerCase()}`}
                  className={`rounded-md ${getChangeColor(s.change_pct)} ${getCellSize(s.change_pct)} flex flex-col items-center justify-center px-2 py-1 cursor-default transition-all hover:brightness-110 hover:scale-105`}
                  style={{ minWidth: "70px", flex: "1 1 70px", maxWidth: "110px" }}
                  title={`${s.symbol}: ${s.ltp ? `₹${s.ltp.toFixed(2)}` : ""} | ${s.change_pct >= 0 ? "+" : ""}${s.change_pct?.toFixed(2)}%`}
                >
                  <span className="font-mono text-[10px] font-bold leading-tight truncate w-full text-center">{s.symbol}</span>
                  <span className="font-mono text-xs font-bold">{s.change_pct >= 0 ? "+" : ""}{s.change_pct?.toFixed(1)}%</span>
                  {s.ltp && <span className="text-[9px] opacity-70">{s.ltp.toFixed(0)}</span>}
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
