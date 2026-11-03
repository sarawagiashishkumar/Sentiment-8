import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { Button } from "components/ui/button";
import { RefreshCw, Shield, TrendingDown, Activity, BarChart3 } from "lucide-react";
import { TVChart } from "components/Shared/TVChartWrapper";

const API = "/api";

function MetricCard({ label, value, sub, icon: Icon, color = "text-white" }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3" data-testid={`risk-metric-${label.toLowerCase().replace(/\s/g, "-")}`}>
      <div className="flex items-center gap-2 mb-1">
        {Icon && <Icon size={12} className="text-slate-500" />}
        <p className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</p>
      </div>
      <p className={`text-lg font-bold font-mono ${color}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export function RiskDashboard({ authHeaders }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchRisk = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/risk/portfolio-summary`, { headers: authHeaders });
      setData(res.data);
    } catch (err) {
      console.error("Risk fetch failed:", err?.message);
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => { fetchRisk(); }, [fetchRisk]);

  const ecSource = data?.equity_curve || [];
  const equityCurve = ecSource.map((pt, i) => ({
    time: Math.floor(Date.now() / 1000) - (ecSource.length - i) * 86400,
    value: pt.equity,
  }));

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="risk-dashboard">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2">
          <Shield size={16} className="text-amber-400" /> Risk Dashboard
        </CardTitle>
        <Button onClick={fetchRisk} disabled={loading} className="h-7 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3" data-testid="risk-refresh">
          <RefreshCw size={12} className={loading ? "animate-spin mr-1" : "mr-1"} /> Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {data ? (
          <>
            {/* Position overview */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="risk-overview">
              <MetricCard label="Open Positions" value={data.open_positions} icon={Activity} />
              <MetricCard label="Unique Symbols" value={data.unique_symbols} icon={BarChart3} />
              <MetricCard label="Max Drawdown (30d)" value={`${data.drawdown.max_drawdown_30d_pct}%`} icon={TrendingDown} color={data.drawdown.max_drawdown_30d_pct > 10 ? "text-rose-400" : "text-amber-400"} sub={`${data.drawdown.closed_trades_30d} closed trades`} />
              <MetricCard label="Correlated Pairs" value={data.correlation.correlated_pairs} icon={Shield} color={data.correlation.correlated_pairs > 3 ? "text-amber-400" : "text-emerald-400"} />
            </div>

            {/* Greeks */}
            <div data-testid="risk-greeks">
              <p className="text-[10px] text-slate-500 uppercase mb-1">Aggregate Greeks</p>
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-2 text-center">
                  <p className="text-[9px] text-slate-500">Net Delta</p>
                  <p className={`text-sm font-bold font-mono ${data.greeks.net_delta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{data.greeks.net_delta}</p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-2 text-center">
                  <p className="text-[9px] text-slate-500">Net Theta</p>
                  <p className={`text-sm font-bold font-mono ${data.greeks.net_theta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{data.greeks.net_theta}</p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-2 text-center">
                  <p className="text-[9px] text-slate-500">Net Vega</p>
                  <p className="text-sm font-bold font-mono text-cyan-300">{data.greeks.net_vega}</p>
                </div>
              </div>
            </div>

            {/* Margin */}
            <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-3" data-testid="risk-margin">
              <p className="text-[10px] text-slate-500 uppercase mb-1">Margin Utilization</p>
              <p className="text-lg font-bold font-mono text-white">{data.margin.total_required > 0 ? `Rs.${data.margin.total_required.toLocaleString("en-IN")}` : "No open margin"}</p>
            </div>

            {/* Concentration */}
            {data.concentration.length > 0 && (
              <div data-testid="risk-concentration">
                <p className="text-[10px] text-slate-500 uppercase mb-1">Position Concentration</p>
                <div className="space-y-1">
                  {data.concentration.map(c => (
                    <div key={c.symbol} className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-300 w-20 truncate">{c.symbol}</span>
                      <div className="flex-1 h-2.5 bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-cyan-500/70 transition-all" style={{ width: `${Math.min(c.pct, 100)}%` }} />
                      </div>
                      <span className="text-[10px] font-mono text-slate-400 w-10 text-right">{c.pct}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Equity curve */}
            {equityCurve.length > 2 && (
              <div data-testid="risk-equity-curve">
                <p className="text-[10px] text-slate-500 uppercase mb-1">Equity Curve (30d)</p>
                <TVChart data={equityCurve} type="area" height={160} />
              </div>
            )}

            {/* Empty state */}
            {data.open_positions === 0 && data.drawdown.closed_trades_30d === 0 && (
              <div className="text-center py-4" data-testid="risk-empty">
                <Shield size={24} className="mx-auto text-slate-700 mb-1" />
                <p className="text-xs text-slate-500">No open positions or recent trades</p>
                <p className="text-[10px] text-slate-600 mt-0.5">Risk metrics populate as you trade through F&O signals</p>
              </div>
            )}
          </>
        ) : loading ? (
          <p className="text-sm text-slate-400 text-center animate-pulse">Loading risk metrics...</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
