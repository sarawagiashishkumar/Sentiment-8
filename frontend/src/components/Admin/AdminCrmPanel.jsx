import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MessageSquare, Send, Mail, Users, Eye, Reply, X, Megaphone } from "lucide-react";

const API = "/api";

export function AdminCrmPanel({ authHeaders }) {
  const [inbox, setInbox] = useState([]);
  const [sent, setSent] = useState([]);
  const [tab, setTab] = useState("inbox");
  const [unread, setUnread] = useState(0);
  const [showCompose, setShowCompose] = useState(false);
  const [composeForm, setComposeForm] = useState({ to_user_key: "", subject: "", body: "", priority: "normal" });
  const [users, setUsers] = useState([]);
  const [replyTo, setReplyTo] = useState(null);

  const fetchInbox = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/crm/inbox`, { headers: authHeaders });
      setInbox(res.data.messages || []);
      setUnread(res.data.unread || 0);
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  const fetchSent = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/crm/sent`, { headers: authHeaders });
      setSent(res.data.messages || []);
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      setUsers(res.data || []);
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  useEffect(() => { fetchInbox(); fetchSent(); fetchUsers(); }, [fetchInbox, fetchSent, fetchUsers]);

  const markRead = async (msgId) => {
    await axios.patch(`${API}/admin/crm/read/${msgId}`, {}, { headers: authHeaders });
    fetchInbox();
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!composeForm.subject.trim() || !composeForm.body.trim()) return;
    try {
      await axios.post(`${API}/admin/crm/send`, {
        to_user_key: composeForm.to_user_key || null,
        subject: composeForm.subject,
        body: composeForm.body,
        priority: composeForm.priority,
      }, { headers: authHeaders });
      setComposeForm({ to_user_key: "", subject: "", body: "", priority: "normal" });
      setShowCompose(false);
      fetchSent();
    } catch (err) { console.error(err); }
  };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="admin-crm-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2">
          <MessageSquare size={16} className="text-violet-400" /> CRM Messages
          {unread > 0 && <span className="bg-rose-500 text-white text-[10px] rounded-full px-1.5 py-0.5">{unread}</span>}
        </CardTitle>
        <div className="flex gap-2">
          <Button onClick={() => { setShowCompose(!showCompose); setReplyTo(null); }} className="h-7 bg-violet-600 text-white hover:bg-violet-500 text-xs px-3" data-testid="crm-compose-btn">
            <Send size={12} className="mr-1" /> Compose
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 border-b border-slate-800 pb-2">
          <button onClick={() => setTab("inbox")} className={`text-xs px-3 py-1 rounded ${tab === "inbox" ? "bg-violet-600 text-white" : "text-slate-400"}`} data-testid="crm-tab-inbox">
            <Mail size={12} className="inline mr-1" /> Inbox ({inbox.length})
          </button>
          <button onClick={() => setTab("sent")} className={`text-xs px-3 py-1 rounded ${tab === "sent" ? "bg-violet-600 text-white" : "text-slate-400"}`} data-testid="crm-tab-sent">
            <Send size={12} className="inline mr-1" /> Sent ({sent.length})
          </button>
        </div>

        {showCompose && (
          <form onSubmit={sendMessage} className="space-y-2 rounded-lg border border-violet-700/40 bg-violet-950/20 p-3" data-testid="crm-compose-form">
            <div className="flex gap-2">
              <select value={composeForm.to_user_key} onChange={(e) => setComposeForm(p => ({ ...p, to_user_key: e.target.value }))} className="h-8 flex-1 rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs px-2" data-testid="crm-compose-to">
                <option value="">Broadcast to All Users</option>
                {users.filter(u => u.role !== "owner").map(u => (
                  <option key={u.user_key} value={u.user_key}>{u.username} ({u.role})</option>
                ))}
              </select>
              <select value={composeForm.priority} onChange={(e) => setComposeForm(p => ({ ...p, priority: e.target.value }))} className="h-8 rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs px-2" data-testid="crm-compose-priority">
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <Input value={composeForm.subject} onChange={(e) => setComposeForm(p => ({ ...p, subject: e.target.value }))} placeholder="Subject" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="crm-compose-subject" />
            <textarea value={composeForm.body} onChange={(e) => setComposeForm(p => ({ ...p, body: e.target.value }))} placeholder="Message body..." rows={3} className="w-full rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs p-2 resize-none" data-testid="crm-compose-body" />
            <div className="flex gap-2">
              <Button type="submit" className="h-7 bg-violet-600 text-white hover:bg-violet-500 text-xs" data-testid="crm-compose-send">
                {composeForm.to_user_key ? <><Send size={12} className="mr-1" /> Send</> : <><Megaphone size={12} className="mr-1" /> Broadcast</>}
              </Button>
              <Button type="button" onClick={() => setShowCompose(false)} variant="ghost" className="h-7 text-xs text-slate-400"><X size={12} /></Button>
            </div>
          </form>
        )}

        {tab === "inbox" && (
          <div className="space-y-1.5" data-testid="crm-inbox-list">
            {inbox.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-4">No messages</p>
            ) : inbox.map(msg => (
              <div key={msg.message_id} className={`rounded-lg border px-3 py-2 ${msg.status === "unread" ? "border-violet-500/40 bg-violet-950/20" : "border-slate-700 bg-slate-900/40"}`} data-testid={`crm-msg-${msg.message_id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1">
                    <span className="text-xs font-bold text-white">{msg.from_username}</span>
                    <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${msg.type === "fraud_alert" ? "bg-rose-500/20 text-rose-300" : msg.type === "reactivation_request" ? "bg-amber-500/20 text-amber-300" : "bg-slate-700 text-slate-300"}`}>{msg.type?.replace(/_/g, " ")}</span>
                    <p className="text-xs text-slate-200 mt-0.5">{msg.subject}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5 line-clamp-2">{msg.body}</p>
                    <span className="text-[9px] text-slate-600">{new Date(msg.ts).toLocaleString("en-IN")}</span>
                  </div>
                  <div className="flex flex-col gap-1">
                    {msg.status === "unread" && (
                      <button onClick={() => markRead(msg.message_id)} className="text-[10px] text-violet-400 hover:text-violet-300"><Eye size={12} /></button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "sent" && (
          <div className="space-y-1.5" data-testid="crm-sent-list">
            {sent.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-4">No sent messages</p>
            ) : sent.map(msg => (
              <div key={msg.message_id} className="rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
                <span className="text-xs text-slate-300">To: {msg.to_user_key ? "User" : "All Users"}</span>
                <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${msg.type === "broadcast" ? "bg-blue-500/20 text-blue-300" : "bg-slate-700 text-slate-300"}`}>{msg.type}</span>
                <p className="text-xs text-white mt-0.5">{msg.subject}</p>
                <p className="text-[10px] text-slate-400 mt-0.5 line-clamp-2">{msg.body}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function AdminFraudPanel({ authHeaders }) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("all");

  const fetchIncidents = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/admin/fraud-incidents?status=all`, { headers: authHeaders });
      setIncidents(res.data.incidents || []);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, [authHeaders]);

  useEffect(() => { fetchIncidents(); }, [fetchIncidents]);

  const resolveIncident = async (fraudId, action) => {
    try {
      await axios.post(`${API}/admin/fraud-incidents/${fraudId}/resolve?action=${action}`, {}, { headers: authHeaders });
      fetchIncidents();
    } catch (err) { console.error(err); }
  };

  const pendingCount = incidents.filter(i => i.status === "pending").length;
  const resolvedCount = incidents.filter(i => i.status !== "pending").length;
  const filtered = filter === "all" ? incidents : incidents.filter(i => filter === "pending" ? i.status === "pending" : i.status !== "pending");

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="admin-fraud-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2 text-sm">
          <Users size={16} className="text-rose-400" /> Fraud Detection
          {pendingCount > 0 && <span className="bg-rose-500 text-white text-[10px] rounded-full px-1.5 py-0.5">{pendingCount}</span>}
        </CardTitle>
        <Button onClick={fetchIncidents} className="h-7 bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs px-3" data-testid="fraud-refresh-btn">Refresh</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Summary Cards */}
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-2 text-center">
            <p className="text-lg font-bold text-white">{incidents.length}</p>
            <p className="text-[9px] text-slate-500">Total Incidents</p>
          </div>
          <div className="rounded-lg border border-rose-700/40 bg-rose-950/20 p-2 text-center">
            <p className="text-lg font-bold text-rose-400">{pendingCount}</p>
            <p className="text-[9px] text-slate-500">Pending</p>
          </div>
          <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/20 p-2 text-center">
            <p className="text-lg font-bold text-emerald-400">{resolvedCount}</p>
            <p className="text-[9px] text-slate-500">Resolved</p>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-2 border-b border-slate-800 pb-2">
          {[["all", "All"], ["pending", "Pending"], ["resolved", "Resolved"]].map(([k, label]) => (
            <button key={k} onClick={() => setFilter(k)} className={`text-xs px-3 py-1 rounded ${filter === k ? "bg-rose-600 text-white" : "text-slate-400"}`} data-testid={`fraud-filter-${k}`}>
              {label}
            </button>
          ))}
        </div>

        {/* Incident List */}
        {filtered.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-3">No {filter === "all" ? "" : filter} fraud incidents</p>
        ) : filtered.map(inc => (
          <div key={inc.fraud_id} className={`rounded-lg border px-3 py-2 ${inc.status === "pending" ? "border-rose-500/40 bg-rose-950/20" : "border-slate-700 bg-slate-900/40"}`} data-testid={`fraud-${inc.fraud_id}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-white">{inc.username || "Unknown"}</span>
                  <span className={`text-[10px] px-1.5 rounded ${inc.status === "pending" ? "bg-rose-500/20 text-rose-300" : inc.status === "confirmed" ? "bg-amber-500/20 text-amber-300" : "bg-emerald-500/20 text-emerald-300"}`}>{inc.status}</span>
                  {inc.details?.detection_type && <span className="text-[9px] text-violet-400 bg-violet-950/30 px-1.5 rounded">{inc.details.detection_type}</span>}
                </div>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  {inc.details?.current_location && <>{inc.details.current_location} &mdash; </>}
                  {inc.details?.distance_km && <>{inc.details.distance_km}km in {inc.details.elapsed_hours}h ({inc.details.required_speed_kmh} km/h)</>}
                </p>
                {inc.details?.previous_location && (
                  <p className="text-[9px] text-slate-500">From: {inc.details.previous_location}</p>
                )}
                <span className="text-[9px] text-slate-600">{inc.created_at ? new Date(inc.created_at).toLocaleString("en-IN") : ""}</span>
                {inc.resolved_at && <span className="text-[9px] text-slate-600 ml-2">Resolved: {new Date(inc.resolved_at).toLocaleString("en-IN")}</span>}
              </div>
              {inc.status === "pending" && (
                <div className="flex flex-col gap-1">
                  <Button onClick={() => resolveIncident(inc.fraud_id, "reactivate")} className="h-6 bg-emerald-600 text-white text-[10px] px-2" data-testid={`fraud-reactivate-${inc.fraud_id}`}>Reactivate</Button>
                  <Button onClick={() => resolveIncident(inc.fraud_id, "confirm")} className="h-6 bg-rose-600 text-white text-[10px] px-2" data-testid={`fraud-confirm-${inc.fraud_id}`}>Confirm</Button>
                </div>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function AdminPermissionsPanel({ authHeaders }) {
  const [users, setUsers] = useState([]);
  const [packages, setPackages] = useState({});
  const [defaultCosts, setDefaultCosts] = useState({});
  const [defaultLimits, setDefaultLimits] = useState({});
  const [selectedUser, setSelectedUser] = useState(null);
  const [perms, setPerms] = useState(null);
  const [editPackage, setEditPackage] = useState("");
  const [editLimits, setEditLimits] = useState({});
  const [editRestrictions, setEditRestrictions] = useState([]);
  const [editCosts, setEditCosts] = useState({});
  const [showEditor, setShowEditor] = useState(false);
  const [saving, setSaving] = useState(false);
  // Package CRUD
  const [showPkgCreate, setShowPkgCreate] = useState(false);
  const [pkgForm, setPkgForm] = useState({ key: "", label: "", credits: 0, limits: {} });
  const [editPkgKey, setEditPkgKey] = useState(null);
  // Global fee editor
  const [showFeeEditor, setShowFeeEditor] = useState(false);
  const [feeEdits, setFeeEdits] = useState({});
  const [feeSaving, setFeeSaving] = useState(false);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      setUsers(res.data || []);
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  const fetchPackages = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/packages`, { headers: authHeaders });
      setPackages(res.data.packages || {});
      setDefaultCosts(res.data.default_feature_costs || {});
      setDefaultLimits(res.data.default_usage_limits || {});
      setFeeEdits(res.data.default_feature_costs || {});
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  useEffect(() => { fetchUsers(); fetchPackages(); }, [fetchUsers, fetchPackages]);

  const viewPermissions = async (userKey) => {
    try {
      const res = await axios.get(`${API}/admin/users/${userKey}/permissions`, { headers: authHeaders });
      setPerms(res.data);
      setSelectedUser(userKey);
      setEditPackage(res.data.package || "free");
      setEditLimits({ ...(res.data.usage_limits || {}) });
      setEditCosts({ ...(res.data.feature_costs || {}) });
      setEditRestrictions([...(res.data.feature_restrictions || [])]);
      setShowEditor(false);
    } catch (err) { console.error(err); }
  };

  const savePermissions = async () => {
    if (!selectedUser) return;
    setSaving(true);
    try {
      await axios.patch(`${API}/admin/users/${selectedUser}/permissions`, {
        package: editPackage,
        usage_limits: editLimits,
        feature_costs: editCosts,
        feature_restrictions: editRestrictions,
      }, { headers: authHeaders });
      await viewPermissions(selectedUser);
    } catch (err) { console.error(err); }
    setSaving(false);
  };

  const toggleRestriction = (feature) => {
    setEditRestrictions(prev =>
      prev.includes(feature) ? prev.filter(f => f !== feature) : [...prev, feature]
    );
  };

  // Package CRUD handlers
  const openCreatePkg = () => {
    setPkgForm({ key: "", label: "", credits: 0, limits: {} });
    setEditPkgKey(null);
    setShowPkgCreate(true);
  };
  const openEditPkg = (key) => {
    const pkg = packages[key];
    setPkgForm({ key, label: pkg.label, credits: pkg.credits, limits: { ...(pkg.limits || {}) } });
    setEditPkgKey(key);
    setShowPkgCreate(true);
  };
  const savePkg = async () => {
    if (!pkgForm.key.trim() || !pkgForm.label.trim()) return;
    try {
      await axios.post(`${API}/admin/packages`, {
        key: pkgForm.key.trim().toLowerCase().replace(/\s+/g, "_"),
        label: pkgForm.label.trim(),
        credits: Number(pkgForm.credits),
        limits: pkgForm.limits,
      }, { headers: authHeaders });
      setShowPkgCreate(false);
      await fetchPackages();
    } catch (err) { console.error(err); }
  };
  const deletePkg = async (key) => {
    try {
      await axios.delete(`${API}/admin/packages/${key}`, { headers: authHeaders });
      await fetchPackages();
    } catch (err) { console.error("Delete pkg:", err?.response?.data?.detail || err?.message); }
  };

  // Global fee save
  const saveGlobalFees = async () => {
    setFeeSaving(true);
    try {
      await axios.patch(`${API}/admin/feature-costs`, { costs: feeEdits }, { headers: authHeaders });
      await fetchPackages();
      setShowFeeEditor(false);
    } catch (err) { console.error(err); }
    setFeeSaving(false);
  };

  const FEATURE_LABELS = {
    fno_generate: "F&O Signal Generation",
    multibagger_generate: "Multibagger Screener",
    portfolio_analyze: "Portfolio Analysis",
    custom_position: "Custom Position Tracking",
    backtest_run: "Strategy Backtester",
    iv_collect: "IV Data Collection",
    reports_view: "Reports Access",
    watchlist_add: "Watchlist Management",
    alert_rule_create: "Alert Rule Creation",
  };

  const LIMIT_LABELS = {
    fno_generate_daily: "F&O Generations / Day",
    multibagger_generate_daily: "Multibagger Scans / Day",
    portfolio_analyze_daily: "Portfolio Analyses / Day",
    custom_position_total: "Max Custom Positions",
    backtest_run_daily: "Backtests / Day",
    alert_rules_total: "Max Alert Rules",
    watchlist_items_total: "Max Watchlist Items",
  };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="admin-permissions-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2 text-sm">
          <Users size={16} className="text-cyan-400" /> Permissions & Packages
        </CardTitle>
        <div className="flex gap-2">
          <Button onClick={() => setShowFeeEditor(!showFeeEditor)} variant="outline" className="h-7 border-amber-700 bg-amber-900/30 text-amber-300 hover:bg-amber-800/50 text-[10px] px-2" data-testid="global-fee-toggle-btn">
            Global Fees
          </Button>
          <Button onClick={openCreatePkg} className="h-7 bg-cyan-600 text-white hover:bg-cyan-500 text-[10px] px-2" data-testid="create-package-btn">
            + New Plan
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Global Fee Editor */}
        {showFeeEditor && (
          <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-3 space-y-2" data-testid="global-fee-editor">
            <p className="text-xs font-bold text-amber-300">Global Default Feature Costs (credits per use)</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {Object.entries(FEATURE_LABELS).map(([key, label]) => (
                <div key={key} className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="text-slate-300">{label}</span>
                  <input
                    type="number" step="0.1" min="0"
                    value={feeEdits[key] ?? 0}
                    onChange={(e) => setFeeEdits(p => ({ ...p, [key]: parseFloat(e.target.value) || 0 }))}
                    className="w-20 h-6 rounded border border-slate-700 bg-slate-800 text-slate-100 text-[10px] px-1.5 text-right"
                    data-testid={`global-fee-${key}`}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2 pt-1">
              <Button onClick={saveGlobalFees} disabled={feeSaving} className="h-7 bg-amber-600 text-white text-[10px] px-3" data-testid="global-fee-save-btn">
                {feeSaving ? "Saving..." : "Save Global Fees"}
              </Button>
              <Button onClick={() => setShowFeeEditor(false)} variant="ghost" className="h-7 text-[10px] text-slate-400">Cancel</Button>
            </div>
          </div>
        )}

        {/* Package Create/Edit Form */}
        {showPkgCreate && (
          <div className="rounded-lg border border-cyan-700/40 bg-cyan-950/20 p-3 space-y-2" data-testid="pkg-create-form">
            <p className="text-xs font-bold text-cyan-300">{editPkgKey ? `Edit Plan: ${editPkgKey}` : "Create New Plan"}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div>
                <label className="text-[9px] text-slate-400">Key (ID)</label>
                <Input value={pkgForm.key} onChange={(e) => setPkgForm(p => ({ ...p, key: e.target.value }))} placeholder="e.g. starter" className="h-7 text-xs border-slate-700 bg-slate-800 text-slate-100" disabled={!!editPkgKey} data-testid="pkg-key-input" />
              </div>
              <div>
                <label className="text-[9px] text-slate-400">Label</label>
                <Input value={pkgForm.label} onChange={(e) => setPkgForm(p => ({ ...p, label: e.target.value }))} placeholder="Starter Pack" className="h-7 text-xs border-slate-700 bg-slate-800 text-slate-100" data-testid="pkg-label-input" />
              </div>
              <div>
                <label className="text-[9px] text-slate-400">Credits</label>
                <Input type="number" min="0" value={pkgForm.credits} onChange={(e) => setPkgForm(p => ({ ...p, credits: Number(e.target.value) }))} className="h-7 text-xs border-slate-700 bg-slate-800 text-slate-100" data-testid="pkg-credits-input" />
              </div>
            </div>
            <p className="text-[9px] text-slate-400 font-semibold mt-1">Usage Limits for this Plan</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {Object.entries(LIMIT_LABELS).map(([key, label]) => (
                <div key={key} className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="text-slate-300">{label}</span>
                  <input
                    type="number" min="0"
                    value={pkgForm.limits[key] ?? defaultLimits[key] ?? 0}
                    onChange={(e) => setPkgForm(p => ({ ...p, limits: { ...p.limits, [key]: parseInt(e.target.value) || 0 } }))}
                    className="w-20 h-6 rounded border border-slate-700 bg-slate-800 text-slate-100 text-[10px] px-1.5 text-right"
                    data-testid={`pkg-limit-${key}`}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2 pt-1">
              <Button onClick={savePkg} className="h-7 bg-cyan-600 text-white text-[10px] px-3" data-testid="pkg-save-btn">{editPkgKey ? "Update Plan" : "Create Plan"}</Button>
              <Button onClick={() => setShowPkgCreate(false)} variant="ghost" className="h-7 text-[10px] text-slate-400">Cancel</Button>
            </div>
          </div>
        )}

        {/* Package Tiers Overview */}
        <div className="overflow-x-auto scrollbar-hide">
          <p className="text-[10px] text-slate-400 font-semibold mb-2">Available Tiers</p>
          <div className="flex gap-2 min-w-max pb-1">
            {Object.entries(packages).map(([key, pkg]) => (
              <div key={key} className="rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2 min-w-[130px] relative group" data-testid={`package-card-${key}`}>
                <p className="text-xs font-bold text-white">{pkg.label}</p>
                <p className="text-[10px] text-cyan-400">{pkg.credits === 999999 ? "Unlimited" : pkg.credits} credits</p>
                <p className="text-[9px] text-slate-500 mt-0.5">FNO: {pkg.limits?.fno_generate_daily === 999999 ? "Unlim" : pkg.limits?.fno_generate_daily}/day</p>
                <p className="text-[9px] text-slate-500">Alerts: {pkg.limits?.alert_rules_total === 999999 ? "Unlim" : pkg.limits?.alert_rules_total} max</p>
                <div className="absolute top-1 right-1 hidden group-hover:flex gap-0.5">
                  <button onClick={() => openEditPkg(key)} className="text-[9px] text-cyan-400 hover:text-cyan-300 bg-slate-800 rounded px-1" data-testid={`pkg-edit-${key}`}>Edit</button>
                  {key !== "free" && (
                    <button onClick={() => deletePkg(key)} className="text-[9px] text-rose-400 hover:text-rose-300 bg-slate-800 rounded px-1" data-testid={`pkg-delete-${key}`}>Del</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {/* User List */}
          <div className="space-y-1.5">
            <p className="text-[10px] text-slate-400 font-semibold">Select User</p>
            {users.map(u => (
              <button key={u.user_key} onClick={() => viewPermissions(u.user_key)} className={`w-full text-left rounded px-3 py-2 text-xs flex items-center justify-between ${selectedUser === u.user_key ? "bg-cyan-600/20 border border-cyan-500/40" : "bg-slate-900/40 border border-slate-700 hover:border-slate-600"}`} data-testid={`perm-user-${u.user_key}`}>
                <div>
                  <span className="font-bold text-white">{u.username}</span>
                  <span className="ml-2 text-slate-500">{u.role}</span>
                </div>
                <span className="text-[9px] text-slate-600">{u.credits ?? 0} cr</span>
              </button>
            ))}
          </div>

          {/* Permission Details + Editor */}
          {perms && (
            <div className="space-y-3" data-testid="perm-details">
              <div className="flex items-center justify-between">
                <p className="text-xs text-white font-bold">{perms.username}</p>
                <div className="flex gap-1">
                  <Button onClick={() => setShowEditor(!showEditor)} className="h-6 bg-slate-700 text-slate-200 text-[10px] px-2" data-testid="perm-edit-toggle">
                    {showEditor ? "Cancel" : "Edit"}
                  </Button>
                  {showEditor && (
                    <Button onClick={savePermissions} disabled={saving} className="h-6 bg-cyan-600 text-white text-[10px] px-2" data-testid="perm-save-all">
                      {saving ? "Saving..." : "Save All"}
                    </Button>
                  )}
                </div>
              </div>

              {perms.suspended && <p className="text-[10px] text-rose-400 font-bold bg-rose-950/30 rounded px-2 py-1">ACCOUNT SUSPENDED</p>}

              {/* Package Assignment */}
              <div>
                <p className="text-[10px] text-slate-400 font-semibold mb-1">Package Tier</p>
                <div className="flex items-center gap-2">
                  <select value={editPackage} onChange={(e) => setEditPackage(e.target.value)} disabled={!showEditor} className="h-7 flex-1 rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs px-2 disabled:opacity-50" data-testid="perm-package-select">
                    {Object.entries(packages).map(([k, v]) => <option key={k} value={k}>{v.label} ({v.credits === 999999 ? "Unlim" : v.credits} credits)</option>)}
                  </select>
                </div>
              </div>

              {/* Usage Limits Editor */}
              <div>
                <p className="text-[10px] text-slate-400 font-semibold mb-1">Usage Limits</p>
                <div className="space-y-1">
                  {Object.entries(LIMIT_LABELS).map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between gap-2 text-[10px]">
                      <span className="text-slate-300 flex-1">{label}</span>
                      {showEditor ? (
                        <input
                          type="number"
                          value={editLimits[key] ?? defaultLimits[key] ?? 0}
                          onChange={(e) => setEditLimits(p => ({ ...p, [key]: parseInt(e.target.value) || 0 }))}
                          className="w-20 h-6 rounded border border-slate-700 bg-slate-800 text-slate-100 text-[10px] px-1.5 text-right"
                          data-testid={`limit-${key}`}
                        />
                      ) : (
                        <span className="text-slate-200 font-mono">
                          {(perms.usage_limits?.[key] ?? 0) === 999999 ? "Unlimited" : (perms.usage_limits?.[key] ?? 0)}
                          {perms.current_usage?.[key.replace("_daily", "_today").replace("_total", "_total")] !== undefined && (
                            <span className="ml-1 text-cyan-400">({perms.current_usage[key.replace("_daily", "_today").replace("_total", "_total")]} used)</span>
                          )}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Feature Credit Costs Editor */}
              <div>
                <p className="text-[10px] text-slate-400 font-semibold mb-1">Credit Cost per Feature (User Override)</p>
                <div className="space-y-1">
                  {Object.entries(FEATURE_LABELS).map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between gap-2 text-[10px]">
                      <span className="text-slate-300 flex-1">{label}</span>
                      {showEditor ? (
                        <input
                          type="number"
                          step="0.1"
                          value={editCosts[key] ?? defaultCosts[key] ?? 0}
                          onChange={(e) => setEditCosts(p => ({ ...p, [key]: parseFloat(e.target.value) || 0 }))}
                          className="w-20 h-6 rounded border border-slate-700 bg-slate-800 text-slate-100 text-[10px] px-1.5 text-right"
                          data-testid={`cost-${key}`}
                        />
                      ) : (
                        <span className="text-slate-200 font-mono">{perms.feature_costs?.[key] ?? defaultCosts[key] ?? 0} cr</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Feature Restrictions Toggle */}
              <div>
                <p className="text-[10px] text-slate-400 font-semibold mb-1">Feature Access (toggle to restrict)</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(FEATURE_LABELS).map(([key, label]) => {
                    const restricted = showEditor ? editRestrictions.includes(key) : (perms.feature_restrictions || []).includes(key);
                    return (
                      <button
                        key={key}
                        onClick={() => showEditor && toggleRestriction(key)}
                        disabled={!showEditor}
                        className={`rounded-md px-2 py-1 text-[9px] font-medium border transition-all ${
                          restricted
                            ? "bg-rose-950/40 border-rose-500/40 text-rose-300"
                            : "bg-emerald-950/30 border-emerald-500/30 text-emerald-300"
                        } ${showEditor ? "cursor-pointer hover:opacity-80" : "cursor-default opacity-70"}`}
                        data-testid={`restrict-${key}`}
                      >
                        {restricted ? "Blocked" : "Allowed"}: {label.split(" ")[0]}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
