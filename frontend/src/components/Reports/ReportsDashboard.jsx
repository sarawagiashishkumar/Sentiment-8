import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RefreshCw, Download, Calendar, TrendingUp, TrendingDown, BarChart3 } from "lucide-react";
import { Input } from "@/components/ui/input";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function StatCard({ label, value, positive, icon: Icon }) {
  const getColor = () => {
    if (positive === true) return "text-emerald-400";
    if (positive === false) return "text-rose-400";
    return "text-white";
  };
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-center">
      {Icon && <Icon size={14} className="mx-auto mb-1 text-slate-500" />}
      <p className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-bold font-mono mt-0.5 ${getColor()}`}>{value}</p>
    </div>
  );
}

export function ReportsDashboard({ authHeaders }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState("daily");
  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split("T")[0]);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    try {
      const endpoint = period === "daily"
        ? `${API}/reports/daily-summary?date=${selectedDate}`
        : `${API}/reports/weekly-summary`;
      const res = await axios.get(endpoint, { headers: authHeaders });
      setReport(res.data);
    } catch (err) {
      console.error("Report fetch failed:", err?.message);
    } finally {
      setLoading(false);
    }
  }, [authHeaders, period, selectedDate]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const exportCSV = () => {
    if (!report?.journal_entries?.length) return;
    const headers = ["Time", "Event", "Symbol", "Direction", "Entry", "Exit", "P&L", "Score", "Quality"];
    const rows = report.journal_entries.map(e => [
      e.ts || "", e.event_type || "", e.symbol || "", e.direction || "",
      e.entry_price || "", e.exit_price || "", e.pnl || "", e.confluence_score || "", e.signal_quality || "",
    ]);
    const csv = [headers, ...rows].map(r => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `report_${period}_${selectedDate}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="space-y-4" data-testid="reports-page">
      <Card className="border-slate-800 bg-slate-950/70">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <CardTitle className="text-white flex items-center gap-2">
            <BarChart3 size={18} className="text-cyan-400" /> Reports
          </CardTitle>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Period toggle */}
            <div className="flex rounded-md border border-slate-700 overflow-hidden">
              {["daily", "weekly"].map(p => (
                <button key={p} onClick={() => setPeriod(p)} data-testid={`report-period-${p}`}
                  className={`px-3 py-1 text-xs font-medium transition-colors ${period === p ? "bg-cyan-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"}`}>
                  {p.charAt(0).toUpperCase() + p.slice(1)}
                </button>
              ))}
            </div>
            {period === "daily" && (
              <div className="flex items-center gap-1">
                <Calendar size={13} className="text-slate-500" />
                <Input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)}
                  className="h-7 w-36 border-slate-700 bg-slate-900 text-xs text-slate-200" data-testid="report-date-picker" />
              </div>
            )}
            <Button onClick={fetchReport} disabled={loading} className="h-7 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3" data-testid="report-refresh">
              <RefreshCw size={12} className={loading ? "animate-spin mr-1" : "mr-1"} /> Refresh
            </Button>
            <Button onClick={exportCSV} disabled={!report?.journal_entries?.length} className="h-7 bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs px-3" data-testid="report-export-csv">
              <Download size={12} className="mr-1" /> CSV
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {report ? (
            <>
              {/* Period label */}
              <p className="text-xs text-slate-500 font-mono" data-testid="report-period-label">
                {report.period === "daily" ? `Daily Report: ${report.date}` : `Weekly Report: ${report.from_date} — ${report.to_date}`}
              </p>

              {/* Summary cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2" data-testid="report-summary-cards">
                <StatCard label="Signals" value={report.total_signals} icon={BarChart3} />
                <StatCard label="Closed" value={report.closed_trades} />
                <StatCard label="P&L" value={`${report.total_pnl >= 0 ? "+" : ""}${report.total_pnl}`} positive={report.total_pnl >= 0} />
                <StatCard label="Wins" value={report.wins} positive />
                <StatCard label="Losses" value={report.losses} positive={false} />
                <StatCard label="Win Rate" value={`${report.win_rate}%`} positive={report.win_rate >= 50} />
              </div>

              {/* Best/Worst + Performance */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {report.best_trade && (
                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-900/10 p-2.5">
                    <p className="text-[9px] text-emerald-400 uppercase">Best Trade</p>
                    <p className="font-mono text-sm text-emerald-300 font-bold">{report.best_trade.symbol}: +{report.best_trade.pnl?.toFixed(2)}</p>
                  </div>
                )}
                {report.worst_trade && (
                  <div className="rounded-lg border border-rose-500/20 bg-rose-900/10 p-2.5">
                    <p className="text-[9px] text-rose-400 uppercase">Worst Trade</p>
                    <p className="font-mono text-sm text-rose-300 font-bold">{report.worst_trade.symbol}: {report.worst_trade.pnl?.toFixed(2)}</p>
                  </div>
                )}
                <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-2.5">
                  <p className="text-[9px] text-slate-400 uppercase">Gen Performance</p>
                  <p className="font-mono text-sm text-cyan-300">{report.generation_runs} runs, avg {(report.avg_generation_ms / 1000).toFixed(1)}s</p>
                </div>
              </div>

              {/* Top symbols */}
              {report.top_symbols?.length > 0 && (
                <div data-testid="report-top-symbols">
                  <p className="text-[10px] text-slate-500 mb-1">Top Symbols</p>
                  <div className="flex flex-wrap gap-1.5">
                    {report.top_symbols.map(s => (
                      <span key={s.symbol} className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-cyan-300">
                        {s.symbol} ({s.count})
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Quality distribution */}
              {Object.keys(report.quality_distribution || {}).length > 0 && (
                <div data-testid="report-quality-dist">
                  <p className="text-[10px] text-slate-500 mb-1">Signal Quality Distribution</p>
                  <div className="flex gap-2">
                    {Object.entries(report.quality_distribution).map(([q, c]) => (
                      <span key={q} className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium ${
                        q === "HIGH" ? "bg-emerald-900/40 text-emerald-300" :
                        q === "MEDIUM" ? "bg-amber-900/40 text-amber-300" :
                        "bg-slate-800 text-slate-400"
                      }`}>{q}: {c}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {report.total_signals === 0 && report.closed_trades === 0 && (
                <div className="text-center py-6" data-testid="report-empty">
                  <BarChart3 size={28} className="mx-auto text-slate-700 mb-2" />
                  <p className="text-xs text-slate-500">No trading activity for this period</p>
                  <p className="text-[10px] text-slate-600 mt-1">Reports auto-populate as you generate signals and manage positions</p>
                </div>
              )}
            </>
          ) : loading ? (
            <p className="text-sm text-slate-400 text-center animate-pulse">Loading report...</p>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
