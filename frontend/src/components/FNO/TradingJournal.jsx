import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { RefreshCw, BookOpen, TrendingUp, TrendingDown, Filter, Search, X } from "lucide-react";

const API = "/api";

const EVENT_LABELS = {
  signal_generated: { label: "Signal", color: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30" },
  position_opened: { label: "Opened", color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
  position_closed: { label: "Closed", color: "bg-violet-500/20 text-violet-300 border-violet-500/30" },
  position_updated: { label: "Updated", color: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
};

export function TradingJournal({ authHeaders }) {
  const [entries, setEntries] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState("");
  const [filterSymbol, setFilterSymbol] = useState("");

  const fetchJournal = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filterType) params.set("event_type", filterType);
      if (filterSymbol) params.set("symbol", filterSymbol.toUpperCase());
      const res = await axios.get(`${API}/journal?${params}`, { headers: authHeaders });
      setEntries(res.data.entries || []);
      setSummary(res.data.summary || null);
    } catch (err) { console.error("Journal fetch failed:", err?.message); }
    finally { setLoading(false); }
  }, [authHeaders, filterType, filterSymbol]);

  useEffect(() => { fetchJournal(); }, [fetchJournal]);

  return (
    <div className="space-y-4" data-testid="trading-journal">
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2" data-testid="journal-summary">
          <SummaryCard label="Total Entries" value={summary.total_entries} />
          <SummaryCard label="Closed Trades" value={summary.closed_trades} />
          <SummaryCard label="Total P&L" value={`${summary.total_pnl >= 0 ? "+" : ""}${summary.total_pnl}`} positive={summary.total_pnl >= 0} />
          <SummaryCard label="Wins" value={summary.wins} positive />
          <SummaryCard label="Losses" value={summary.losses} positive={false} />
          <SummaryCard label="Win Rate" value={`${summary.win_rate}%`} positive={summary.win_rate >= 50} />
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="journal-filters">
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-300 focus:border-cyan-500 focus:outline-none"
          data-testid="journal-filter-type"
        >
          <option value="">All Events</option>
          <option value="signal_generated">Signals</option>
          <option value="position_opened">Opened</option>
          <option value="position_closed">Closed</option>
          <option value="position_updated">Updated</option>
        </select>

        <div className="relative">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value)}
            placeholder="Filter symbol..."
            className="bg-slate-900 border border-slate-700 rounded-md pl-6 pr-6 py-1 text-xs text-slate-200 w-32 focus:border-cyan-500 focus:outline-none"
            data-testid="journal-filter-symbol"
          />
          {filterSymbol && (
            <button onClick={() => setFilterSymbol("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
              <X size={11} />
            </button>
          )}
        </div>

        <Button onClick={fetchJournal} disabled={loading} className="h-7 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3" data-testid="journal-refresh">
          <RefreshCw size={12} className={loading ? "animate-spin mr-1" : "mr-1"} />
          Refresh
        </Button>

        <span className="ml-auto text-[10px] text-slate-500 font-mono" data-testid="journal-count">
          {entries.length} entries
        </span>
      </div>

      {/* Journal Table */}
      {entries.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-slate-700" data-testid="journal-table">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="bg-slate-800/80 text-slate-400">
                <th className="px-2 py-1.5 text-left font-medium">Time</th>
                <th className="px-2 py-1.5 text-left font-medium">Event</th>
                <th className="px-2 py-1.5 text-left font-medium">Symbol</th>
                <th className="px-2 py-1.5 text-left font-medium">Dir</th>
                <th className="px-2 py-1.5 text-right font-medium">Entry</th>
                <th className="px-2 py-1.5 text-right font-medium">Exit</th>
                <th className="px-2 py-1.5 text-right font-medium">P&L</th>
                <th className="px-2 py-1.5 text-right font-medium">Score</th>
                <th className="px-2 py-1.5 text-left font-medium">Quality</th>
                <th className="px-2 py-1.5 text-left font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => {
                const evtCfg = EVENT_LABELS[e.event_type] || { label: e.event_type, color: "bg-slate-800 text-slate-400" };
                const pnl = e.pnl || 0;
                return (
                  <tr key={`${e.ts}-${i}`} className={i % 2 === 0 ? "bg-slate-900/40" : "bg-slate-950/40"}>
                    <td className="px-2 py-1 font-mono text-slate-500 whitespace-nowrap">
                      {e.ts ? new Date(e.ts).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "--"}
                    </td>
                    <td className="px-2 py-1">
                      <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium border ${evtCfg.color}`}>{evtCfg.label}</span>
                    </td>
                    <td className="px-2 py-1 font-mono font-semibold text-slate-200">{e.symbol || "--"}</td>
                    <td className="px-2 py-1">
                      {e.direction === "BULLISH" ? (
                        <span className="text-emerald-400 flex items-center gap-0.5"><TrendingUp size={9} />CE</span>
                      ) : e.direction === "BEARISH" ? (
                        <span className="text-rose-400 flex items-center gap-0.5"><TrendingDown size={9} />PE</span>
                      ) : (
                        <span className="text-slate-500">--</span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-slate-300">{e.entry_price ? `${e.entry_price.toFixed(2)}` : "--"}</td>
                    <td className="px-2 py-1 text-right font-mono text-slate-300">{e.exit_price ? `${e.exit_price.toFixed(2)}` : "--"}</td>
                    <td className={`px-2 py-1 text-right font-mono font-bold ${pnl > 0 ? "text-emerald-400" : pnl < 0 ? "text-rose-400" : "text-slate-500"}`}>
                      {e.event_type === "position_closed" ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}` : "--"}
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-cyan-300">{e.confluence_score ? Math.round(e.confluence_score) : "--"}</td>
                    <td className="px-2 py-1">
                      {e.signal_quality ? (
                        <span className={`text-[9px] font-medium ${
                          e.signal_quality === "HIGH" ? "text-emerald-400" :
                          e.signal_quality === "MEDIUM" ? "text-amber-400" : "text-slate-400"
                        }`}>{e.signal_quality}</span>
                      ) : "--"}
                    </td>
                    <td className="px-2 py-1 text-slate-500 max-w-[120px] truncate">{e.notes || "--"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : !loading ? (
        <div className="flex flex-col items-center justify-center py-8 text-center" data-testid="journal-empty">
          <BookOpen size={28} className="text-slate-700 mb-2" />
          <p className="text-xs text-slate-500">No journal entries yet</p>
          <p className="text-[10px] text-slate-600 mt-1">Entries auto-log when you generate F&O signals or manage positions</p>
        </div>
      ) : null}
    </div>
  );
}

function SummaryCard({ label, value, positive }) {
  const getTextColor = () => {
    if (positive === true) return "text-emerald-400";
    if (positive === false) return "text-rose-400";
    return "text-white";
  };

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-2 text-center">
      <p className="text-[9px] text-slate-500 uppercase tracking-wider">{label}</p>
      <p className={`text-sm font-bold font-mono mt-0.5 ${getTextColor()}`}>{value}</p>
    </div>
  );
}
