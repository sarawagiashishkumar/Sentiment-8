import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MessageSquare, Send, Mail, Users, Eye, Reply, X, Megaphone } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="admin-fraud-panel">
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2 text-sm">
          <Users size={16} className="text-rose-400" /> Fraud Detection
          {incidents.filter(i => i.status === "pending").length > 0 && (
            <span className="bg-rose-500 text-white text-[10px] rounded-full px-1.5 py-0.5">{incidents.filter(i => i.status === "pending").length}</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {incidents.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-3">No fraud incidents</p>
        ) : incidents.map(inc => (
          <div key={inc.fraud_id} className={`rounded-lg border px-3 py-2 ${inc.status === "pending" ? "border-rose-500/40 bg-rose-950/20" : "border-slate-700 bg-slate-900/40"}`} data-testid={`fraud-${inc.fraud_id}`}>
            <div className="flex items-center justify-between gap-2">
              <div>
                <span className="text-xs font-bold text-white">{inc.username || "Unknown"}</span>
                <span className={`ml-2 text-[10px] px-1.5 rounded ${inc.status === "pending" ? "bg-rose-500/20 text-rose-300" : "bg-emerald-500/20 text-emerald-300"}`}>{inc.status}</span>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  {inc.details?.current_location} - {inc.details?.distance_km}km in {inc.details?.elapsed_hours}h ({inc.details?.required_speed_kmh} km/h)
                </p>
                <span className="text-[9px] text-slate-600">{inc.created_at ? new Date(inc.created_at).toLocaleString("en-IN") : ""}</span>
              </div>
              {inc.status === "pending" && (
                <div className="flex gap-1">
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
  const [selectedUser, setSelectedUser] = useState(null);
  const [perms, setPerms] = useState(null);
  const [editPackage, setEditPackage] = useState("");

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
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  useEffect(() => { fetchUsers(); fetchPackages(); }, [fetchUsers, fetchPackages]);

  const viewPermissions = async (userKey) => {
    try {
      const res = await axios.get(`${API}/admin/users/${userKey}/permissions`, { headers: authHeaders });
      setPerms(res.data);
      setSelectedUser(userKey);
      setEditPackage(res.data.package || "free");
    } catch (err) { console.error(err); }
  };

  const updatePackage = async () => {
    if (!selectedUser) return;
    try {
      await axios.patch(`${API}/admin/users/${selectedUser}/permissions`, { package: editPackage }, { headers: authHeaders });
      viewPermissions(selectedUser);
    } catch (err) { console.error(err); }
  };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="admin-permissions-panel">
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2 text-sm">
          <Users size={16} className="text-cyan-400" /> Permissions & Packages
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <p className="text-[10px] text-slate-400 font-semibold">Users</p>
            {users.map(u => (
              <button key={u.user_key} onClick={() => viewPermissions(u.user_key)} className={`w-full text-left rounded px-2 py-1.5 text-xs ${selectedUser === u.user_key ? "bg-cyan-600/20 border border-cyan-500/40" : "bg-slate-900/40 border border-slate-700 hover:border-slate-600"}`} data-testid={`perm-user-${u.user_key}`}>
                <span className="font-bold text-white">{u.username}</span>
                <span className="ml-2 text-slate-400">{u.role}</span>
              </button>
            ))}
          </div>

          {perms && (
            <div className="space-y-2" data-testid="perm-details">
              <p className="text-[10px] text-slate-400 font-semibold">{perms.username} - Permissions</p>
              <div className="flex items-center gap-2">
                <select value={editPackage} onChange={(e) => setEditPackage(e.target.value)} className="h-7 rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs px-2" data-testid="perm-package-select">
                  {Object.entries(packages).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <Button onClick={updatePackage} className="h-7 bg-cyan-600 text-white text-[10px] px-3" data-testid="perm-save-package">Apply</Button>
              </div>
              {perms.suspended && <p className="text-[10px] text-rose-400 font-bold">ACCOUNT SUSPENDED</p>}
              <div className="text-[10px] text-slate-400 space-y-0.5">
                <p>Package: <span className="text-white font-bold">{perms.package_label}</span></p>
                {Object.entries(perms.usage_limits || {}).map(([k, v]) => (
                  <p key={k}>{k}: <span className="text-slate-200">{v === 999999 ? "Unlimited" : v}</span>
                    {perms.current_usage?.[k.replace("_daily", "_today").replace("_total", "_total")] !== undefined && (
                      <span className="ml-1 text-cyan-400">({perms.current_usage[k.replace("_daily", "_today").replace("_total", "_total")]} used)</span>
                    )}
                  </p>
                ))}
                {perms.feature_restrictions?.length > 0 && (
                  <p className="text-rose-400">Restricted: {perms.feature_restrictions.join(", ")}</p>
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
