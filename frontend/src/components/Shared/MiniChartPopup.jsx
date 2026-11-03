import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { X, TrendingUp, TrendingDown } from "lucide-react";
import { TVChart } from "components/Shared/TVChartWrapper";

const API = "/api";

/**
 * Mini intraday chart popup — shown when clicking a stock tile in heatmaps.
 */
export function MiniChartPopup({ symbol, authHeaders, onClose }) {
  const [chartData, setChartData] = useState([]);
  const [stockInfo, setStockInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchChart = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/market/stock-chart/${symbol}`, { headers: authHeaders, timeout: 10000 });
      const candles = (res.data?.candles || []).map(c => ({
        time: Math.floor(new Date(c.date || c.time).getTime() / 1000),
        open: c.open, high: c.high, low: c.low, close: c.close,
      }));
      setChartData(candles);
      setStockInfo(res.data?.info || null);
    } catch (err) {
      console.error("Chart fetch failed:", err?.message);
      setChartData([]);
    } finally {
      setLoading(false);
    }
  }, [symbol, authHeaders]);

  useEffect(() => { fetchChart(); }, [fetchChart]);

  if (!symbol) return null;

  const lastCandle = chartData[chartData.length - 1];
  const firstCandle = chartData[0];
  const changePct = lastCandle && firstCandle && firstCandle.open > 0
    ? ((lastCandle.close - firstCandle.open) / firstCandle.open * 100).toFixed(2)
    : null;
  const isUp = changePct && Number(changePct) >= 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="mini-chart-overlay">
      <div className="relative mx-4 w-full max-w-lg rounded-xl border border-slate-700 bg-slate-950 p-4 shadow-2xl" data-testid="mini-chart-popup">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-sm text-white">{symbol}</span>
            {changePct !== null && (
              <span className={`flex items-center gap-0.5 text-xs font-mono font-bold ${isUp ? "text-emerald-400" : "text-rose-400"}`}>
                {isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {isUp ? "+" : ""}{changePct}%
              </span>
            )}
            {lastCandle && (
              <span className="text-xs font-mono text-slate-400">LTP: {lastCandle.close.toFixed(2)}</span>
            )}
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:text-white hover:bg-slate-800" data-testid="mini-chart-close">
            <X size={16} />
          </button>
        </div>

        {/* Chart */}
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <p className="text-xs text-slate-500 animate-pulse">Loading chart data...</p>
          </div>
        ) : chartData.length > 0 ? (
          <TVChart data={chartData} type="candlestick" height={240} />
        ) : (
          <div className="flex items-center justify-center h-48">
            <p className="text-xs text-slate-500">No chart data available. Ensure Market Data API is connected.</p>
          </div>
        )}

        {/* Info row */}
        {stockInfo && (
          <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-slate-500">
            {stockInfo.open && <span>O: {stockInfo.open.toFixed(2)}</span>}
            {stockInfo.high && <span>H: {stockInfo.high.toFixed(2)}</span>}
            {stockInfo.low && <span>L: {stockInfo.low.toFixed(2)}</span>}
            {stockInfo.volume && <span>Vol: {stockInfo.volume.toLocaleString("en-IN")}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
