import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Bell, Plus, Trash2, RefreshCw, ToggleLeft, ToggleRight, Zap } from "lucide-react";

const API = "/api";

const FIELD_OPTIONS = [
  { value: "symbol_ltp", label: "Symbol LTP (Price)" },
  { value: "symbol_change_pct", label: "Symbol Change %" },
  { value: "symbol_volume", label: "Symbol Volume" },
  { value: "symbol_high", label: "Symbol Day High" },
  { value: "symbol_low", label: "Symbol Day Low" },
  { value: "vix", label: "India VIX" },
];
const OP_OPTIONS = [
  { value: "gt", label: ">" },
  { value: "lt", label: "<" },
  { value: "gte", label: ">=" },
  { value: "lte", label: "<=" },
  { value: "eq", label: "=" },
];

export function AlertRuleEngine({ authHeaders }) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [evalResult, setEvalResult] = useState(null);

  const [form, setForm] = useState({ name: "", logic: "AND", conditions: [{ field: "symbol_ltp", symbol: "", operator: "gt", value: "" }] });

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/alerts/rules`, { headers: authHeaders });
      setRules(res.data.rules || []);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [authHeaders]);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const addCondition = () => {
    setForm(p => ({ ...p, conditions: [...p.conditions, { field: "symbol_ltp", symbol: "", operator: "gt", value: "" }] }));
  };

  const removeCondition = (idx) => {
    setForm(p => ({ ...p, conditions: p.conditions.filter((_, i) => i !== idx) }));
  };

  const updateCondition = (idx, key, val) => {
    setForm(p => ({ ...p, conditions: p.conditions.map((c, i) => i === idx ? { ...c, [key]: val } : c) }));
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || form.conditions.length === 0) return;
    try {
      await axios.post(`${API}/alerts/rules`, {
        name: form.name,
        logic: form.logic,
        conditions: form.conditions.map(c => ({ ...c, value: Number(c.value) })),
      }, { headers: authHeaders });
      setForm({ name: "", logic: "AND", conditions: [{ field: "symbol_ltp", symbol: "", operator: "gt", value: "" }] });
      setShowForm(false);
      fetchRules();
    } catch (err) { console.error(err); }
  };

  const toggleRule = async (ruleId, currentEnabled) => {
    try {
      await axios.patch(`${API}/alerts/rules/${ruleId}`, { enabled: !currentEnabled }, { headers: authHeaders });
      fetchRules();
    } catch (err) { console.error(err); }
  };

  const deleteRule = async (ruleId) => {
    try {
      await axios.delete(`${API}/alerts/rules/${ruleId}`, { headers: authHeaders });
      fetchRules();
    } catch (err) { console.error(err); }
  };

  const evaluateNow = async () => {
    try {
      const res = await axios.post(`${API}/alerts/evaluate`, {}, { headers: authHeaders });
      setEvalResult(res.data);
    } catch (err) { console.error(err); }
  };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="alert-rule-engine">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2">
          <Zap size={16} className="text-amber-400" /> Custom Alert Rules
        </CardTitle>
        <div className="flex gap-2">
          <Button onClick={evaluateNow} className="h-7 bg-amber-600 text-white hover:bg-amber-500 text-xs px-3" data-testid="alert-evaluate-btn">
            <RefreshCw size={12} className="mr-1" /> Evaluate Now
          </Button>
          <Button onClick={() => setShowForm(!showForm)} className="h-7 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3" data-testid="alert-create-btn">
            <Plus size={12} className="mr-1" /> New Rule
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {evalResult && (
          <div className="rounded-lg border border-amber-600/40 bg-amber-950/30 p-2.5 text-xs" data-testid="alert-eval-result">
            <span className="text-amber-300">Evaluated {evalResult.evaluated} rules</span>
            {evalResult.triggered?.length > 0 && (
              <span className="ml-2 text-amber-200 font-bold">{evalResult.triggered.length} triggered!</span>
            )}
          </div>
        )}

        {showForm && (
          <form onSubmit={handleCreate} className="space-y-3 rounded-lg border border-slate-700 bg-slate-900/50 p-3" data-testid="alert-rule-form">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="text-[10px] text-slate-400 mb-1 block">Rule Name</label>
                <Input value={form.name} onChange={(e) => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. NIFTY Above 24000" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="alert-rule-name" />
              </div>
              <div>
                <label className="text-[10px] text-slate-400 mb-1 block">Logic</label>
                <select value={form.logic} onChange={(e) => setForm(p => ({ ...p, logic: e.target.value }))} className="h-8 rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs px-2" data-testid="alert-rule-logic">
                  <option value="AND">ALL (AND)</option>
                  <option value="OR">ANY (OR)</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-slate-400 font-semibold">Conditions</p>
              {form.conditions.map((cond, idx) => (
                <div key={`cond-${idx}`} className="flex gap-1.5 items-center flex-wrap">
                  <select value={cond.field} onChange={(e) => updateCondition(idx, "field", e.target.value)} className="h-7 rounded border border-slate-700 bg-slate-800 text-slate-100 text-[10px] px-1.5" data-testid={`alert-cond-field-${idx}`}>
                    {FIELD_OPTIONS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                  </select>
                  {cond.field !== "vix" && (
                    <Input value={cond.symbol} onChange={(e) => updateCondition(idx, "symbol", e.target.value.toUpperCase())} placeholder="Symbol" className="w-24 h-7 border-slate-700 bg-slate-800 text-slate-100 text-[10px]" data-testid={`alert-cond-symbol-${idx}`} />
                  )}
                  <select value={cond.operator} onChange={(e) => updateCondition(idx, "operator", e.target.value)} className="h-7 rounded border border-slate-700 bg-slate-800 text-slate-100 text-[10px] px-1.5" data-testid={`alert-cond-op-${idx}`}>
                    {OP_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <Input type="number" value={cond.value} onChange={(e) => updateCondition(idx, "value", e.target.value)} placeholder="Value" className="w-24 h-7 border-slate-700 bg-slate-800 text-slate-100 text-[10px]" data-testid={`alert-cond-value-${idx}`} />
                  {form.conditions.length > 1 && (
                    <button type="button" onClick={() => removeCondition(idx)} className="text-rose-400 hover:text-rose-300 p-0.5"><Trash2 size={12} /></button>
                  )}
                </div>
              ))}
              <button type="button" onClick={addCondition} className="text-[10px] text-cyan-400 hover:text-cyan-300">+ Add Condition</button>
            </div>
            <Button type="submit" className="h-7 bg-emerald-600 text-white hover:bg-emerald-500 text-xs" data-testid="alert-rule-submit">Create Rule</Button>
          </form>
        )}

        {rules.length > 0 ? (
          <div className="space-y-1.5" data-testid="alert-rules-list">
            {rules.map(rule => (
              <div key={rule.rule_id} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2" data-testid={`alert-rule-${rule.rule_id}`}>
                <div className="flex items-center gap-3 flex-wrap">
                  <Bell size={12} className={rule.enabled ? "text-amber-400" : "text-slate-600"} />
                  <span className="font-mono font-bold text-xs text-white">{rule.name}</span>
                  <span className="text-[10px] text-slate-500">{rule.conditions?.length} condition{rule.conditions?.length !== 1 ? "s" : ""} ({rule.logic})</span>
                  {rule.trigger_count > 0 && <span className="text-[10px] text-amber-400">Fired {rule.trigger_count}x</span>}
                  {rule.last_triggered && <span className="text-[9px] text-slate-500">Last: {new Date(rule.last_triggered).toLocaleTimeString("en-IN")}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => toggleRule(rule.rule_id, rule.enabled)} className="p-1" data-testid={`alert-toggle-${rule.rule_id}`}>
                    {rule.enabled ? <ToggleRight size={16} className="text-emerald-400" /> : <ToggleLeft size={16} className="text-slate-600" />}
                  </button>
                  <button onClick={() => deleteRule(rule.rule_id)} className="text-slate-600 hover:text-rose-400 p-1" data-testid={`alert-delete-${rule.rule_id}`}>
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : !loading ? (
          <div className="text-center py-4" data-testid="alert-rules-empty">
            <Zap size={24} className="mx-auto text-slate-700 mb-1" />
            <p className="text-xs text-slate-500">No alert rules yet</p>
            <p className="text-[10px] text-slate-600 mt-0.5">{"Create rules like \"NIFTY > 24000 AND VIX > 15\" to get notified"}</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
