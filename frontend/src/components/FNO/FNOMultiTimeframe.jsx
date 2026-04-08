import { useCallback, useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, Layers } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const trendColors = {
  BULLISH: "text-emerald-400 border-emerald-500/50 bg-emerald-900/20",
  BEARISH: "text-rose-400 border-rose-500/50 bg-rose-900/20",
  NEUTRAL: "text-slate-400 border-slate-600/50 bg-slate-800/20",
};

const alignColors = {
  STRONGLY_BULLISH: "text-emerald-300 bg-emerald-900/40 border-emerald-500/60",
  BULLISH: "text-emerald-400 bg-emerald-900/20 border-emerald-500/40",
  STRONGLY_BEARISH: "text-rose-300 bg-rose-900/40 border-rose-500/60",
  BEARISH: "text-rose-400 bg-rose-900/20 border-rose-500/40",
  MIXED: "text-amber-400 bg-amber-900/20 border-amber-500/40",
};

export function FNOMultiTimeframe({ authHeaders }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    if (!symbol.trim()) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/fno/multi-timeframe/${symbol.trim().toUpperCase()}`, { headers: authHeaders });
      setData(res.data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [authHeaders, symbol]);

  return (
    <div className="space-y-3" data-testid="fno-multi-timeframe">
      {/* Controls */}
      <div className="flex items-center gap-2">
        <Input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Symbol (e.g. RELIANCE)"
          className="w-44 border-slate-700 bg-slate-800 text-slate-100 text-xs h-8"
          data-testid="mtf-symbol-input"
        />
        <Button
          onClick={fetchData} disabled={loading}
          className="h-8 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3"
          data-testid="mtf-fetch-btn"
        >
          <RefreshCw size={13} className={loading ? "animate-spin mr-1" : "mr-1"} />
          {loading ? "Loading..." : "Analyze"}
        </Button>
      </div>

      {/* Results */}
      {!data ? (
        <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-6 text-center text-slate-500 text-sm" data-testid="mtf-empty">
          <Layers size={24} className="mx-auto mb-2 opacity-50" />
          Enter a symbol and click Analyze for multi-timeframe view.
        </div>
      ) : !data.data_available ? (
        <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-6 text-center text-slate-500 text-sm">
          {data.message || "No data available for this symbol."}
        </div>
      ) : (
        <div className="space-y-2">
          {/* Alignment Badge */}
          <div className="flex items-center gap-2">
            <Badge className={`border px-2 py-0.5 text-xs font-bold ${alignColors[data.alignment] || alignColors.MIXED}`} data-testid="mtf-alignment">
              {data.alignment?.replace(/_/g, " ")}
            </Badge>
            <span className="text-xs text-slate-500">{data.symbol} | {data.bullish_frames} bullish, {data.bearish_frames} bearish</span>
          </div>

          {/* Per-frame cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" data-testid="mtf-frames">
            {["daily", "weekly", "monthly"].map((key) => {
              const frame = data.frames?.[key];
              if (!frame) return null;
              const ind = frame.indicators || {};
              const tc = trendColors[frame.trend] || trendColors.NEUTRAL;
              return (
                <div key={key} className={`rounded-md border p-2.5 ${tc}`} data-testid={`mtf-frame-${key}`}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-bold">{frame.label}</span>
                    <Badge className={`text-[10px] border ${tc}`}>{frame.trend}</Badge>
                  </div>
                  <div className="space-y-0.5 text-[11px]">
                    <Row label="RSI" value={ind.rsi} color={ind.rsi > 70 ? "text-rose-300" : ind.rsi < 30 ? "text-emerald-300" : "text-slate-300"} />
                    <Row label="MACD" value={ind.macd_direction} color={ind.macd_direction === "BULLISH" ? "text-emerald-300" : "text-rose-300"} />
                    <Row label="BB %" value={`${ind.bb_position_pct}%`} />
                    <Row label="Volume" value={ind.volume_trend} color={ind.volume_trend === "RISING" ? "text-emerald-300" : ind.volume_trend === "DECLINING" ? "text-rose-300" : "text-slate-400"} />
                    <Row label="Change" value={`${ind.price_change_pct > 0 ? "+" : ""}${ind.price_change_pct}%`} color={ind.price_change_pct >= 0 ? "text-emerald-300" : "text-rose-300"} />
                    <Row label="Range" value={`${ind.low} - ${ind.high}`} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, color = "text-slate-300" }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={color}>{value}</span>
    </div>
  );
}
