import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { BarChart3, TrendingUp, TrendingDown, Activity, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { Button } from "components/ui/button";
import { Badge } from "components/ui/badge";

const API = "/api";

export function FNOSignalHistory({ authHeaders }) {
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [signalLog, setSignalLog] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("stats");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, histRes, logRes] = await Promise.all([
        axios.get(`${API}/fno/performance-stats`, { headers: authHeaders }),
        axios.get(`${API}/fno/signal-history?limit=50`, { headers: authHeaders }),
        axios.get(`${API}/fno/signal-log?limit=50`, { headers: authHeaders }),
      ]);
      setStats(statsRes.data);
      setHistory(histRes.data.history || []);
      setSignalLog(logRes.data.log || []);
    } catch (err) { console.error("FNOSignalHistory fetch error:", err.message); }
    finally { setLoading(false); }
  }, [authHeaders]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const hasData = stats && stats.total > 0;
  const hasLog = signalLog.length > 0;

  return (
    <div className="space-y-3" data-testid="fno-signal-history">
      {/* Tab bar */}
      <div className="flex items-center gap-2">
        <div className="flex rounded-md border border-slate-700 overflow-hidden">
          {[
            { key: "stats", label: "Performance" },
            { key: "history", label: "Closed Trades" },
            { key: "log", label: "Signal Log" },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === t.key
                  ? "bg-cyan-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-slate-200"
              }`}
              data-testid={`history-tab-${t.key}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <Button
          variant="ghost" size="sm" onClick={fetchData} disabled={loading}
          className="h-7 w-7 p-0 text-slate-400 hover:text-cyan-300"
          data-testid="history-refresh"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      {/* Stats Tab */}
      {activeTab === "stats" && (
        <div className="space-y-3">
          {!hasData ? (
            <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-6 text-center text-slate-500 text-sm" data-testid="no-performance-data">
              <Activity size={24} className="mx-auto mb-2 opacity-50" />
              No closed trades yet. Performance stats will appear once signals reach terminal states (T1/T2 hit, SL triggered, or expired).
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="performance-summary">
                <StatCard label="Total Trades" value={stats.total} icon={<Activity size={16} />} />
                <StatCard
                  label="Win Rate"
                  value={`${stats.win_rate}%`}
                  icon={<BarChart3 size={16} />}
                  color={stats.win_rate >= 50 ? "text-emerald-400" : "text-rose-400"}
                />
                <StatCard
                  label="Avg P&L"
                  value={`${stats.avg_pnl_pct > 0 ? "+" : ""}${stats.avg_pnl_pct}%`}
                  icon={stats.avg_pnl_pct >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                  color={stats.avg_pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"}
                />
                <StatCard
                  label="W / L / N"
                  value={`${stats.wins} / ${stats.losses} / ${stats.neutral}`}
                  icon={<BarChart3 size={16} />}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <StatCard label="Best Trade" value={`+${stats.best_trade_pnl}%`} color="text-emerald-400" />
                <StatCard label="Worst Trade" value={`${stats.worst_trade_pnl}%`} color="text-rose-400" />
              </div>
              {Object.keys(stats.by_symbol).length > 0 && (
                <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-3" data-testid="by-symbol-breakdown">
                  <p className="text-xs text-slate-400 mb-2 font-semibold">By Symbol</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                    {Object.entries(stats.by_symbol).map(([sym, d]) => (
                      <div key={sym} className="rounded bg-slate-800/70 px-2 py-1 text-xs">
                        <span className="text-cyan-300 font-mono">{sym}</span>
                        <span className="ml-1 text-slate-400">
                          {d.wins}W/{d.losses}L ({d.win_rate}%) avg {d.avg_pnl > 0 ? "+" : ""}{d.avg_pnl}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Closed Trades Tab */}
      {activeTab === "history" && (
        <div className="space-y-1.5" data-testid="closed-trades-list">
          {history.length === 0 ? (
            <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-6 text-center text-slate-500 text-sm">
              No closed trades yet.
            </div>
          ) : (
            history.map((h, i) => (
              <div key={h.signal_id || i} className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs flex items-center gap-2 flex-wrap" data-testid={`history-row-${i}`}>
                <span className="font-mono text-cyan-200">{h.option_symbol || h.symbol}</span>
                <Badge className={`border text-[10px] ${
                  h.outcome === "win" ? "border-emerald-500 text-emerald-300 bg-emerald-900/30" :
                  h.outcome === "loss" ? "border-rose-500 text-rose-300 bg-rose-900/30" :
                  "border-slate-500 text-slate-300 bg-slate-800/30"
                }`}>
                  {h.signal_state || h.outcome?.toUpperCase()}
                </Badge>
                <span className={`font-semibold ${(h.pnl_pct || 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {(h.pnl_pct || 0) > 0 ? "+" : ""}{(h.pnl_pct || 0).toFixed(2)}%
                </span>
                <span className="text-slate-500">{h.direction}</span>
                <span className="text-slate-600 ml-auto">{h.close_reason}</span>
              </div>
            ))
          )}
        </div>
      )}

      {/* Signal Log Tab */}
      {activeTab === "log" && (
        <div className="space-y-1.5" data-testid="signal-log-list">
          {!hasLog ? (
            <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-6 text-center text-slate-500 text-sm">
              No signals logged yet. Generate F&O Projections to start logging.
            </div>
          ) : (
            signalLog.map((s, i) => (
              <div key={`${s.option_symbol || s.symbol}-${s.generated_at || i}`} className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs flex items-center gap-2 flex-wrap" data-testid={`log-row-${i}`}>
                <span className="font-mono text-cyan-200">{s.option_symbol || s.symbol}</span>
                <Badge className="border border-slate-600 text-slate-300 bg-slate-800/30 text-[10px]">
                  {s.signal_quality || "N/A"}
                </Badge>
                <span className="text-slate-400">{s.direction}</span>
                <span className="text-slate-400">Entry: {s.entry_price?.toLocaleString("en-IN")}</span>
                <span className="text-slate-400">Score: {s.confluence_score}</span>
                {s.not_affordable && <span className="text-rose-400 font-semibold">OVER BUDGET</span>}
                <span className="text-slate-600 ml-auto">{s.generated_at ? new Date(s.generated_at).toLocaleString() : ""}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, icon, color = "text-slate-100" }) {
  return (
    <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-2.5">
      <div className="flex items-center gap-1 text-slate-500 text-[10px] mb-0.5">
        {icon} {label}
      </div>
      <div className={`text-sm font-bold ${color}`}>{value}</div>
    </div>
  );
}
