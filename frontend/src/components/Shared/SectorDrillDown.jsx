import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { X, TrendingUp, TrendingDown, Loader2 } from "lucide-react";

const API = "/api";

export function SectorDrillDown({ sector, authHeaders, onClose }) {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [kiteLive, setKiteLive] = useState(false);

  const fetchStocks = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await axios.get(
        `${API}/market/sector-stocks?sector=${encodeURIComponent(sector)}`,
        { headers: authHeaders, timeout: 15000 }
      );
      setStocks(resp.data.stocks || []);
      setKiteLive(resp.data.kite_live || false);
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to load sector stocks");
    } finally {
      setLoading(false);
    }
  }, [sector, authHeaders]);

  useEffect(() => { fetchStocks(); }, [fetchStocks]);

  const gainers = stocks.filter(s => s.change_pct > 0).length;
  const losers = stocks.filter(s => s.change_pct < 0).length;

  return (
    <div
      className="mt-3 rounded-xl border border-cyan-500/30 bg-slate-900/90 p-4 shadow-xl animate-in fade-in slide-in-from-top-2 duration-200"
      data-testid={`sector-drilldown-${sector.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold text-white">{sector}</h3>
          {!loading && (
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-slate-400">{stocks.length} stocks</span>
              <span className="text-emerald-400 flex items-center gap-0.5">
                {gainers}<TrendingUp size={9} />
              </span>
              <span className="text-rose-400 flex items-center gap-0.5">
                {losers}<TrendingDown size={9} />
              </span>
              {kiteLive && (
                <span className="rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 px-1.5 py-0.5">
                  Live
                </span>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          data-testid="sector-drilldown-close"
        >
          <X size={14} />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-slate-400 text-xs justify-center">
          <Loader2 size={14} className="animate-spin" />
          Fetching constituent stocks...
        </div>
      ) : error ? (
        <p className="text-xs text-rose-400 py-2">{error}</p>
      ) : stocks.length === 0 ? (
        <p className="text-xs text-slate-500 py-2">No constituent data available for this sector.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-700" data-testid="sector-drilldown-table">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-800/80 text-slate-400">
                <th className="px-3 py-2 text-left font-medium">Symbol</th>
                <th className="px-3 py-2 text-right font-medium">LTP</th>
                <th className="px-3 py-2 text-right font-medium">% Change</th>
                <th className="px-3 py-2 text-right font-medium">Open</th>
                <th className="px-3 py-2 text-right font-medium">High</th>
                <th className="px-3 py-2 text-right font-medium">Low</th>
                <th className="px-3 py-2 text-right font-medium">Volume</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((s, i) => {
                const isUp = s.change_pct >= 0;
                return (
                  <tr key={s.symbol} className={`${i % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"} hover:bg-slate-800/60`} data-testid={`drilldown-stock-${s.symbol.toLowerCase()}`}>
                    <td className="px-3 py-1.5 font-mono font-semibold text-slate-200">{s.symbol}</td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-200">{s.ltp > 0 ? s.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "--"}</td>
                    <td className={`px-3 py-1.5 text-right font-mono font-bold ${isUp ? "text-emerald-400" : "text-rose-400"}`}>
                      {isUp ? "+" : ""}{s.change_pct.toFixed(2)}%
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-400">{s.open > 0 ? s.open.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "--"}</td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-400">{s.high > 0 ? s.high.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "--"}</td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-400">{s.low > 0 ? s.low.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "--"}</td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-400">{s.volume > 0 ? s.volume.toLocaleString("en-IN") : "--"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
