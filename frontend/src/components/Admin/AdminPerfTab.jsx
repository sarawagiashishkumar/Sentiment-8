import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RefreshCw, Clock, Zap, TrendingUp } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function PhaseBar({ label, ms, maxMs, color }) {
  const pct = maxMs > 0 ? Math.min((ms / maxMs) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2" data-testid={`perf-bar-${label.toLowerCase().replace(/\s/g, "-")}`}>
      <span className="text-[10px] text-slate-400 w-20 text-right truncate">{label}</span>
      <div className="flex-1 h-5 bg-slate-800 rounded-md overflow-hidden relative">
        <div
          className="h-full rounded-md transition-all duration-500 ease-out"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
        <span className="absolute inset-0 flex items-center px-2 text-[10px] font-mono text-white/90">
          {ms > 0 ? `${(ms / 1000).toFixed(2)}s` : "--"}
        </span>
      </div>
    </div>
  );
}

export function AdminPerfTab({ authHeaders }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchTimings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/fno/generation-timings`, { headers: authHeaders });
      setData(res.data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [authHeaders]);

  useEffect(() => { fetchTimings(); }, [fetchTimings]);

  const fno = data?.fno || {};
  const mb = data?.multibagger || {};
  const history = data?.history || [];
  const hasFNO = fno.total_ms > 0;
  const hasMB = mb.total_ms > 0;

  // Find max for bar scaling
  const fnoMax = hasFNO ? Math.max(fno.nifty_ms || 0, fno.banknifty_ms || 0, fno.stocks_ms || 0, fno.assembly_ms || 0) : 1;

  // Split history by type
  const fnoHistory = history.filter(h => h.type === "fno").slice(0, 20);
  const mbHistory = history.filter(h => h.type === "multibagger").slice(0, 20);

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-perf-tab">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2">
          <Zap size={18} className="text-amber-400" /> Generation Performance
        </CardTitle>
        <Button type="button" onClick={fetchTimings} disabled={loading} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400 h-8 px-3 text-xs" data-testid="perf-refresh-btn">
          <RefreshCw size={13} className={loading ? "animate-spin mr-1" : "mr-1"} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">

        {/* Last F&O Generation */}
        <div className="space-y-2" data-testid="perf-fno-section">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Last F&O Generation</h3>
            {hasFNO && (
              <span className="ml-auto text-[10px] font-mono text-slate-500">{fno.ts}</span>
            )}
          </div>
          {hasFNO ? (
            <div className="space-y-1.5">
              <PhaseBar label="NIFTY" ms={fno.nifty_ms || 0} maxMs={fnoMax} color="rgb(6, 182, 212)" />
              <PhaseBar label="BANKNIFTY" ms={fno.banknifty_ms || 0} maxMs={fnoMax} color="rgb(139, 92, 246)" />
              <PhaseBar label="Stocks" ms={fno.stocks_ms || 0} maxMs={fnoMax} color="rgb(16, 185, 129)" />
              <PhaseBar label="Assembly" ms={fno.assembly_ms || 0} maxMs={fnoMax} color="rgb(251, 146, 60)" />
              <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800">
                <span className="text-xs text-slate-400">Total</span>
                <span className="text-sm font-bold font-mono text-white" data-testid="perf-fno-total">
                  {(fno.total_ms / 1000).toFixed(2)}s
                </span>
              </div>
              {fno.signal_count != null && (
                <span className="text-[10px] text-slate-500">Signals generated: {fno.signal_count}</span>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-500 py-2" data-testid="perf-fno-empty">
              {fno.message || "No F&O generation run yet. Run a generation from the F&O Projections page."}
            </p>
          )}
        </div>

        {/* Last Multibagger Generation */}
        <div className="space-y-2" data-testid="perf-mb-section">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">Last Multibagger Generation</h3>
            {hasMB && (
              <span className="ml-auto text-[10px] font-mono text-slate-500">{mb.ts}</span>
            )}
          </div>
          {hasMB ? (
            <div className="space-y-1.5">
              <PhaseBar label="Scan" ms={mb.scan_ms || 0} maxMs={mb.total_ms || 1} color="rgb(16, 185, 129)" />
              <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800">
                <span className="text-xs text-slate-400">Total</span>
                <span className="text-sm font-bold font-mono text-white" data-testid="perf-mb-total">
                  {(mb.total_ms / 1000).toFixed(2)}s
                </span>
              </div>
              <div className="flex gap-3 text-[10px] text-slate-500">
                <span>Candidates: {mb.candidates}</span>
                <span>Potential: {mb.potential}</span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500 py-2" data-testid="perf-mb-empty">
              {mb.message || "No Multibagger generation run yet."}
            </p>
          )}
        </div>

        {/* Historical Runs */}
        {(fnoHistory.length > 0 || mbHistory.length > 0) && (
          <div className="space-y-2" data-testid="perf-history-section">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-slate-400" />
              <h3 className="text-sm font-semibold text-white">Recent Runs</h3>
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-[10px]" data-testid="perf-history-table">
                <thead>
                  <tr className="bg-slate-800/80 text-slate-400">
                    <th className="px-2 py-1.5 text-left font-medium">Type</th>
                    <th className="px-2 py-1.5 text-left font-medium">Timestamp</th>
                    <th className="px-2 py-1.5 text-right font-medium">Total</th>
                    <th className="px-2 py-1.5 text-right font-medium">NIFTY</th>
                    <th className="px-2 py-1.5 text-right font-medium">BANKNIFTY</th>
                    <th className="px-2 py-1.5 text-right font-medium">Stocks</th>
                    <th className="px-2 py-1.5 text-right font-medium">Signals</th>
                  </tr>
                </thead>
                <tbody>
                  {history.slice(0, 20).map((h, i) => (
                    <tr key={`${h.ts}-${i}`} className={i % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"}>
                      <td className="px-2 py-1">
                        <span className={`rounded px-1.5 py-0.5 font-medium ${h.type === "fno" ? "bg-cyan-900/40 text-cyan-300" : "bg-emerald-900/40 text-emerald-300"}`}>
                          {h.type === "fno" ? "F&O" : "MB"}
                        </span>
                      </td>
                      <td className="px-2 py-1 font-mono text-slate-400">{h.ts || "--"}</td>
                      <td className="px-2 py-1 text-right font-mono font-bold text-white">{h.total_ms ? `${(h.total_ms/1000).toFixed(1)}s` : "--"}</td>
                      <td className="px-2 py-1 text-right font-mono text-cyan-300">{h.nifty_ms ? `${(h.nifty_ms/1000).toFixed(1)}s` : "--"}</td>
                      <td className="px-2 py-1 text-right font-mono text-violet-300">{h.banknifty_ms ? `${(h.banknifty_ms/1000).toFixed(1)}s` : "--"}</td>
                      <td className="px-2 py-1 text-right font-mono text-emerald-300">{h.stocks_ms ? `${(h.stocks_ms/1000).toFixed(1)}s` : "--"}</td>
                      <td className="px-2 py-1 text-right font-mono text-slate-300">{h.signal_count ?? h.candidates ?? "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {history.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-2" data-testid="perf-no-history">
            No generation history yet. Performance data will appear after running F&O or Multibagger generations during market hours.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
