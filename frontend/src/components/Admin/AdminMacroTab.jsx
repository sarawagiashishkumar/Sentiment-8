import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";

const API = "/api";

export function AdminMacroTab({ authHeaders }) {
  const [macroData, setMacroData] = useState({ active_events: [], all_events: [] });
  const [saving, setSaving] = useState(false);

  const loadMacroEvents = useCallback(async () => {
    try { const r = await axios.get(`${API}/admin/macro-events`, { headers: authHeaders }); setMacroData(r.data); }
    catch (err) { console.error("Failed to fetch macro events:", err?.message); }
  }, [authHeaders]);

  useEffect(() => { loadMacroEvents(); }, [loadMacroEvents]);

  const toggleEvent = async (key) => {
    const current = macroData.active_events || [];
    const next = current.includes(key) ? current.filter(k => k !== key) : [...current, key];
    setMacroData(p => ({ ...p, active_events: next }));
    setSaving(true);
    try { await axios.post(`${API}/admin/macro-events/update`, { events: next }, { headers: authHeaders }); }
    catch { setMacroData(p => ({ ...p, active_events: current })); }
    finally { setSaving(false); }
  };

  const INTENSITY_COLORS = {
    CRITICAL: "text-rose-400 border-rose-700/60 bg-rose-950/40",
    HIGH: "text-orange-400 border-orange-700/60 bg-orange-950/40",
    MEDIUM: "text-yellow-400 border-yellow-700/60 bg-yellow-950/40",
    LOW: "text-slate-400 border-slate-700/60 bg-slate-900/40",
  };

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-macro-events-card">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-white">Active Macro Events</CardTitle>
          <p className="mt-1 text-xs text-slate-400">Toggle events to influence sector macro bias. Changes apply instantly.</p>
        </div>
        <div className="flex items-center gap-2">
          {saving && <span className="text-xs text-cyan-400" data-testid="macro-events-saving">Saving...</span>}
          <Button type="button" onClick={loadMacroEvents} className="bg-slate-800 text-slate-100 hover:bg-slate-700 h-8 px-3 text-xs" data-testid="admin-macro-events-refresh">Refresh</Button>
        </div>
      </CardHeader>
      <CardContent>
        {macroData.active_events.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5" data-testid="macro-events-active-summary">
            <span className="text-xs text-slate-500">Active:</span>
            {macroData.active_events.map(key => <span key={key} className="rounded-full bg-cyan-900/60 px-2 py-0.5 text-xs font-medium text-cyan-300 border border-cyan-700/50">{key}</span>)}
          </div>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="macro-events-grid">
          {(macroData.all_events || []).map(event => {
            const isActive = macroData.active_events.includes(event.key);
            const ic = INTENSITY_COLORS[event.intensity] || INTENSITY_COLORS.LOW;
            return (
              <button key={event.key} type="button" data-testid={`macro-event-toggle-${event.key}`} onClick={() => toggleEvent(event.key)}
                className={`flex items-start justify-between rounded-lg border p-2.5 text-left transition-all ${isActive ? "border-cyan-500 bg-cyan-900/30 ring-1 ring-cyan-500/40" : "border-slate-700 bg-slate-900/60 hover:border-slate-600"}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`text-xs font-semibold ${isActive ? "text-cyan-300" : "text-slate-300"}`}>{event.key}</span>
                    <span className={`rounded px-1 py-px text-[10px] font-medium border ${ic}`}>{event.intensity}</span>
                  </div>
                  {event.description && <p className="mt-0.5 text-[11px] text-slate-500 leading-tight line-clamp-2">{event.description}</p>}
                  {event.beneficiaries?.length > 0 && <p className="mt-0.5 text-[10px] text-emerald-500/80">+ {event.beneficiaries.slice(0, 3).join(", ")}</p>}
                </div>
                <div className={`ml-2 mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 transition-colors ${isActive ? "border-cyan-400 bg-cyan-400" : "border-slate-600 bg-transparent"}`} />
              </button>
            );
          })}
        </div>
        {macroData.all_events.length === 0 && <p className="text-xs text-slate-500" data-testid="macro-events-empty">No events loaded. Click Refresh to load.</p>}
      </CardContent>
    </Card>
  );
}
