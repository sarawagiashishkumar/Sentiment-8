import { useState, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RefreshCw, Play, TrendingUp, TrendingDown } from "lucide-react";
import { TVChart } from "@/components/Shared/TVChartWrapper";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STRATEGY_TEMPLATES = [
  { id: "momentum_ce", label: "Momentum CE (Bullish)" },
  { id: "momentum_pe", label: "Momentum PE (Bearish)" },
  { id: "straddle", label: "Straddle (Non-directional)" },
  { id: "iron_condor", label: "Iron Condor" },
];

export function StrategyBacktester({ authHeaders }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [strategy, setStrategy] = useState("momentum_ce");
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 3);
    return d.toISOString().split("T")[0];
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().split("T")[0]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const runBacktest = useCallback(async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post(`${API}/fno/run-backtest`, {
        symbol: symbol.toUpperCase(), strategy, date_from: dateFrom, date_to: dateTo,
      }, { headers: authHeaders });
      setResult(res.data);
    } catch (err) {
      console.error("Backtest failed:", err?.message);
      setResult({ error: err?.response?.data?.detail || "Backtest failed. Ensure historical data is available." });
    } finally {
      setLoading(false);
    }
  }, [authHeaders, symbol, strategy, dateFrom, dateTo]);

  // Build equity curve data for chart
  const equityCurve = result?.equity_curve?.map((pt, i) => ({
    time: Math.floor(new Date(pt.date || `2024-01-${i + 1}`).getTime() / 1000),
    value: pt.equity || pt.value || 0,
  })) || [];

  const trades = result?.trades || [];
  const summary = result?.summary || {};

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="backtester-panel">
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2">
          <Play size={16} className="text-cyan-400" /> Strategy Backtester
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Controls */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2" data-testid="backtester-controls">
          <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="Symbol" className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="bt-symbol" />
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="h-9 rounded-md border border-slate-700 bg-slate-800 px-2 text-xs text-slate-100 focus:border-cyan-500" data-testid="bt-strategy">
            {STRATEGY_TEMPLATES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="bt-date-from" />
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="bt-date-to" />
          <Button onClick={runBacktest} disabled={loading} className="bg-cyan-600 text-white hover:bg-cyan-500 text-xs" data-testid="bt-run">
            <RefreshCw size={12} className={loading ? "animate-spin mr-1" : "mr-1"} />
            {loading ? "Running..." : "Run Backtest"}
          </Button>
        </div>

        {/* Error state */}
        {result?.error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-900/10 p-3 text-xs text-rose-300" data-testid="bt-error">{result.error}</div>
        )}

        {/* Results */}
        {result && !result.error && (
          <div className="space-y-4">
            {/* Summary cards */}
            {Object.keys(summary).length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2" data-testid="bt-summary">
                {summary.total_trades != null && <MiniStat label="Total Trades" value={summary.total_trades} />}
                {summary.win_rate != null && <MiniStat label="Win Rate" value={`${summary.win_rate}%`} positive={summary.win_rate >= 50} />}
                {summary.total_pnl != null && <MiniStat label="Total P&L" value={summary.total_pnl.toFixed(2)} positive={summary.total_pnl >= 0} />}
                {summary.max_drawdown != null && <MiniStat label="Max Drawdown" value={`${summary.max_drawdown}%`} positive={false} />}
                {summary.sharpe_ratio != null && <MiniStat label="Sharpe" value={summary.sharpe_ratio.toFixed(2)} positive={summary.sharpe_ratio > 0} />}
                {summary.profit_factor != null && <MiniStat label="Profit Factor" value={summary.profit_factor.toFixed(2)} positive={summary.profit_factor > 1} />}
              </div>
            )}

            {/* Equity curve chart */}
            {equityCurve.length > 0 && (
              <div data-testid="bt-equity-chart">
                <p className="text-[10px] text-slate-500 mb-1">Equity Curve</p>
                <TVChart data={equityCurve} type="area" height={200} />
              </div>
            )}

            {/* Trade log */}
            {trades.length > 0 && (
              <div data-testid="bt-trades">
                <p className="text-[10px] text-slate-500 mb-1">Trade Log ({trades.length} trades)</p>
                <div className="overflow-x-auto rounded-lg border border-slate-700">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="bg-slate-800/80 text-slate-400">
                        <th className="px-2 py-1.5 text-left">Date</th>
                        <th className="px-2 py-1.5 text-left">Type</th>
                        <th className="px-2 py-1.5 text-right">Entry</th>
                        <th className="px-2 py-1.5 text-right">Exit</th>
                        <th className="px-2 py-1.5 text-right">P&L</th>
                        <th className="px-2 py-1.5 text-right">Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.slice(0, 50).map((t, i) => (
                        <tr key={`${t.entry_date}-${i}`} className={i % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"}>
                          <td className="px-2 py-1 font-mono text-slate-400">{t.entry_date || "--"}</td>
                          <td className="px-2 py-1">
                            {t.direction === "LONG" ? <span className="text-emerald-400 flex items-center gap-0.5"><TrendingUp size={9} />Long</span>
                            : <span className="text-rose-400 flex items-center gap-0.5"><TrendingDown size={9} />Short</span>}
                          </td>
                          <td className="px-2 py-1 text-right font-mono text-slate-300">{t.entry_price?.toFixed(2) || "--"}</td>
                          <td className="px-2 py-1 text-right font-mono text-slate-300">{t.exit_price?.toFixed(2) || "--"}</td>
                          <td className={`px-2 py-1 text-right font-mono font-bold ${(t.pnl || 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                            {t.pnl != null ? `${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}` : "--"}
                          </td>
                          <td className="px-2 py-1 text-right font-mono text-slate-500">{t.holding_days ? `${t.holding_days}d` : "--"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* No results */}
            {!equityCurve.length && !trades.length && Object.keys(summary).length === 0 && (
              <p className="text-xs text-slate-500 text-center py-4" data-testid="bt-no-data">
                No backtest results. This may be due to insufficient historical data for the selected period.
              </p>
            )}
          </div>
        )}

        {!result && !loading && (
          <div className="text-center py-6" data-testid="bt-initial">
            <Play size={28} className="mx-auto text-slate-700 mb-2" />
            <p className="text-xs text-slate-500">Select a strategy, symbol, and date range to run a backtest</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MiniStat({ label, value, positive }) {
  const getColor = () => {
    if (positive === true) return "text-emerald-400";
    if (positive === false) return "text-rose-400";
    return "text-white";
  };
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-2 text-center">
      <p className="text-[8px] text-slate-500 uppercase">{label}</p>
      <p className={`text-xs font-bold font-mono ${getColor()}`}>{value}</p>
    </div>
  );
}
