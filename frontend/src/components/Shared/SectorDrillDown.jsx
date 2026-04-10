import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { X, TrendingUp, TrendingDown, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5" data-testid="sector-drilldown-grid">
          {stocks.map((s) => {
            const isUp = s.change_pct >= 0;
            return (
              <div
                key={s.symbol}
                className={`rounded-md border p-2 text-[10px] transition-all hover:brightness-110 ${
                  isUp
                    ? "border-emerald-500/20 bg-emerald-900/20"
                    : "border-rose-500/20 bg-rose-900/20"
                }`}
                data-testid={`drilldown-stock-${s.symbol.toLowerCase()}`}
              >
                <div className="font-semibold text-slate-100 truncate">{s.symbol}</div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="font-mono text-slate-300">
                    {s.ltp > 0 ? s.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "--"}
                  </span>
                  <span className={`font-mono font-bold ${isUp ? "text-emerald-300" : "text-rose-300"}`}>
                    {isUp ? "+" : ""}{s.change_pct.toFixed(2)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
