import { useEffect, useState } from "react";
import axios from "axios";
import { UserCog, Shield, Settings, Globe, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SubTabs } from "@/components/Layout/SubTabs";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const roles = [
  { value: "user", label: "Basic User" },
  { value: "sub_admin", label: "Sub-Admin" },
];

const ADMIN_TABS = [
  { id: "users", label: "User Management & Security", icon: UserCog },
  { id: "controls", label: "Advanced Controls", icon: Settings },
  { id: "macro", label: "Active Macro Events", icon: Calendar },
  { id: "kite", label: "API Connect Integration", icon: Globe },
  { id: "csv", label: "OHLCV CSV Seed Management", icon: Shield },
];

export function AdminDashboard({ authHeaders, me, isAdmin, isOwner, token, hydrateMe }) {
  const [activeTab, setActiveTab] = useState("users");
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminError, setAdminError] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminConfig, setAdminConfig] = useState(null);
  const [csvSeeds, setCsvSeeds] = useState([]);
  const [csvSeedLoading, setCsvSeedLoading] = useState(false);
  const [csvSeedMsg, setCsvSeedMsg] = useState("");
  const [csvUploadSymbol, setCsvUploadSymbol] = useState("");
  const [macroEventsData, setMacroEventsData] = useState({ active_events: [], all_events: [] });
  const [macroEventsSaving, setMacroEventsSaving] = useState(false);
  const [apiControlsEdit, setApiControlsEdit] = useState({ kite_data_enabled: true, moneycontrol_data_enabled: true, strict_live_only: true });
  const [domainForm, setDomainForm] = useState({ domain: "", target_record: "" });
  const [domainDeleteConfirm, setDomainDeleteConfirm] = useState(null);
  const [domainMapStatus, setDomainMapStatus] = useState({});
  const [expandedDnsInstructions, setExpandedDnsInstructions] = useState({});
  const [kiteStatus, setKiteStatus] = useState(null);
  const [createForm, setCreateForm] = useState({ username: "", role: "user", initial_credits: 0, quota_limit: 10 });
  const [usernameEdit, setUsernameEdit] = useState({});
  const [roleEdit, setRoleEdit] = useState({});
  const [creditEdit, setCreditEdit] = useState({});
  const [quotaEdit, setQuotaEdit] = useState({});

  useEffect(() => {
    loadAdminUsers();
    if (isOwner) loadAdminConfig();
    checkKiteStatus();
    loadMacroEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkKiteStatus = async () => {
    try { const r = await axios.get(`${API}/kite/status`, { headers: authHeaders }); setKiteStatus(r.data); } catch { setKiteStatus({ connected: false }); }
  };
  const loadAdminUsers = async () => {
    setAdminLoading(true); setAdminError("");
    try {
      const r = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      const rows = r.data || [];
      setAdminUsers(rows);
      const cm = {}, qm = {}, um = {}, rm = {};
      rows.forEach((row) => { cm[row.user_key] = row.credits; qm[row.user_key] = row.quota_limit; um[row.user_key] = row.username; rm[row.user_key] = row.role; });
      setCreditEdit(cm); setQuotaEdit(qm); setUsernameEdit(um); setRoleEdit(rm);
    } catch (e) { setAdminError(e?.response?.data?.detail || "Unable to load users"); }
    finally { setAdminLoading(false); }
  };
  const loadAdminConfig = async () => {
    try { const r = await axios.get(`${API}/admin/config`, { headers: authHeaders }); setAdminConfig(r.data); if (r.data?.api_controls) setApiControlsEdit(r.data.api_controls); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to load admin config"); }
  };
  const loadMacroEvents = async () => {
    try { const r = await axios.get(`${API}/admin/macro-events`, { headers: authHeaders }); setMacroEventsData(r.data); } catch {}
  };
  const toggleMacroEvent = async (key) => {
    const current = macroEventsData.active_events || [];
    const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
    setMacroEventsData((prev) => ({ ...prev, active_events: next }));
    setMacroEventsSaving(true);
    try { await axios.post(`${API}/admin/macro-events/update`, { events: next }, { headers: authHeaders }); }
    catch { setMacroEventsData((prev) => ({ ...prev, active_events: current })); }
    finally { setMacroEventsSaving(false); }
  };
  const createUser = async (event) => {
    event.preventDefault(); setAdminError("");
    try { await axios.post(`${API}/admin/users`, createForm, { headers: authHeaders }); setCreateForm({ username: "", role: "user", initial_credits: 0, quota_limit: 10 }); await loadAdminUsers(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to create user"); }
  };
  const updateCredits = async (userRef) => {
    try { await axios.patch(`${API}/admin/users/${userRef}/credits`, { credits: Number(creditEdit[userRef] || 0) }, { headers: authHeaders }); await loadAdminUsers(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update credits"); }
  };
  const updateQuota = async (userRef) => {
    try { await axios.patch(`${API}/admin/users/${userRef}/quota`, { quota_limit: Number(quotaEdit[userRef] || 1) }, { headers: authHeaders }); await loadAdminUsers(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update quota"); }
  };
  const updateUserProfile = async (userRef) => {
    try { await axios.patch(`${API}/admin/users/${userRef}/profile`, { username: (usernameEdit[userRef] || "").trim(), role: roleEdit[userRef] }, { headers: authHeaders }); await loadAdminUsers(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update user profile"); }
  };
  const updateOwnUsername = async () => {
    try { await axios.patch(`${API}/admin/self/username`, { username: (usernameEdit[me?.user_key] || "").trim() }, { headers: authHeaders }); await hydrateMe(token); await loadAdminUsers(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update own username"); }
  };
  const deleteUser = async (userRef) => {
    try { await axios.delete(`${API}/admin/users/${userRef}`, { headers: authHeaders }); await loadAdminUsers(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to delete user"); }
  };
  const saveApiControls = async () => {
    try { await axios.patch(`${API}/admin/api-controls`, apiControlsEdit, { headers: authHeaders }); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update API controls"); }
  };
  const addDomainMapping = async (event) => {
    event.preventDefault();
    try { await axios.post(`${API}/admin/domain-mappings`, domainForm, { headers: authHeaders }); setDomainForm({ domain: "", target_record: "" }); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to save domain mapping"); }
  };
  const updateDomainStatus = async (domain, status) => {
    try { await axios.patch(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}`, { status }, { headers: authHeaders }); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to update domain status"); }
  };
  const deleteDomainMapping = async (domain) => {
    try { await axios.delete(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}`, { headers: authHeaders }); setDomainDeleteConfirm(null); await loadAdminConfig(); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to delete domain mapping"); }
  };
  const mapDomain = async (domain) => {
    setDomainMapStatus((prev) => ({ ...prev, [domain]: { loading: true, result: null } }));
    try { const resp = await axios.post(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}/map`, {}, { headers: authHeaders }); setDomainMapStatus((prev) => ({ ...prev, [domain]: { loading: false, result: resp.data } })); await loadAdminConfig(); }
    catch (e) { setDomainMapStatus((prev) => ({ ...prev, [domain]: { loading: false, result: { error: e?.response?.data?.detail || "Map failed" } } })); }
  };
  const loadCsvSeeds = async () => {
    setCsvSeedLoading(true); setCsvSeedMsg("");
    try { const r = await axios.get(`${API}/admin/csv-seeds`, { headers: authHeaders }); setCsvSeeds(r.data.seeds || []); }
    catch (e) { setCsvSeedMsg(e?.response?.data?.detail || "Unable to load CSV seeds"); }
    setCsvSeedLoading(false);
  };
  const uploadCsvSeed = async (e) => {
    e.preventDefault();
    if (!csvUploadSymbol.trim()) { setCsvSeedMsg("Enter a symbol"); return; }
    const fileInput = e.target.querySelector('input[type="file"]');
    if (!fileInput?.files?.[0]) { setCsvSeedMsg("Select a CSV file"); return; }
    const formData = new FormData(); formData.append("file", fileInput.files[0]);
    setCsvSeedLoading(true);
    try { const r = await axios.post(`${API}/admin/csv-seeds/${csvUploadSymbol.trim().toUpperCase()}`, formData, { headers: { ...authHeaders, "Content-Type": "multipart/form-data" } }); setCsvSeedMsg(`Saved ${r.data.symbol}: ${r.data.rows} rows`); setCsvUploadSymbol(""); fileInput.value = ""; await loadCsvSeeds(); }
    catch (e2) { setCsvSeedMsg(e2?.response?.data?.detail || "Upload failed"); }
    setCsvSeedLoading(false);
  };
  const deleteCsvSeed = async (symbol) => {
    try { await axios.delete(`${API}/admin/csv-seeds/${symbol}`, { headers: authHeaders }); setCsvSeedMsg(`Deleted ${symbol}`); await loadCsvSeeds(); }
    catch (e) { setCsvSeedMsg(e?.response?.data?.detail || "Delete failed"); }
  };

  return (
    <section className="space-y-4" data-testid="admin-page">
      <SubTabs tabs={ADMIN_TABS} active={activeTab} onChange={setActiveTab} />

      {/* User Management */}
      {activeTab === "users" && (
      <Card className="result-card border-slate-800 bg-slate-950/70">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <CardTitle className="text-white">User Management & Security</CardTitle>
          <Button type="button" onClick={loadAdminUsers} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-refresh-users-button">
            <UserCog size={16} /> Refresh Users
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={createUser} className="grid grid-cols-1 gap-3 md:grid-cols-5" data-testid="admin-create-user-form">
            <Input value={createForm.username} onChange={(e) => setCreateForm((prev) => ({ ...prev, username: e.target.value }))} placeholder="Username" data-testid="admin-create-username" className="border-slate-700 bg-slate-900 text-slate-100" />
            <select value={createForm.role} onChange={(e) => setCreateForm((prev) => ({ ...prev, role: e.target.value }))} className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-slate-100" data-testid="admin-create-role">
              {roles.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
            </select>
            <Input type="number" min="0" value={createForm.initial_credits} onChange={(e) => setCreateForm((prev) => ({ ...prev, initial_credits: Number(e.target.value) }))} placeholder="Initial Credits" data-testid="admin-create-credits" className="border-slate-700 bg-slate-900 text-slate-100" />
            <Input type="number" min="1" value={createForm.quota_limit} onChange={(e) => setCreateForm((prev) => ({ ...prev, quota_limit: Number(e.target.value) }))} placeholder="Quota" data-testid="admin-create-quota" className="border-slate-700 bg-slate-900 text-slate-100" disabled={createForm.role !== "sub_admin"} />
            <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-create-submit">Create</Button>
          </form>
          {adminError ? <p className="text-sm text-rose-400" data-testid="admin-error">{adminError}</p> : null}
          {adminLoading ? (
            <p className="text-sm text-slate-400" data-testid="admin-loading">Loading users...</p>
          ) : (
            <div className="relative w-full overflow-auto rounded-lg border border-slate-800" data-testid="admin-users-table-wrapper">
              <Table data-testid="admin-users-table">
                <TableHeader className="bg-slate-900">
                  <TableRow>
                    <TableHead>Credential</TableHead><TableHead>Role</TableHead><TableHead>Credits</TableHead><TableHead>Quota</TableHead><TableHead>Created By</TableHead><TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {adminUsers.map((row) => (
                    <TableRow key={row.user_key} className="result-row" data-testid={`admin-row-${row.user_key}`}>
                      <TableCell>
                        <Input value={usernameEdit[row.user_key] ?? row.username} onChange={(e) => setUsernameEdit((prev) => ({ ...prev, [row.user_key]: e.target.value }))} className="h-8 w-44 border-slate-700 bg-slate-900 text-xs text-cyan-200" data-testid={`admin-username-input-${row.user_key}`} disabled={!isOwner && row.user_key !== me?.user_key} />
                      </TableCell>
                      <TableCell>
                        {isOwner ? (
                          <select value={roleEdit[row.user_key] ?? row.role} onChange={(e) => setRoleEdit((prev) => ({ ...prev, [row.user_key]: e.target.value }))} className="h-8 rounded-md border border-slate-700 bg-slate-900 px-2 text-xs text-slate-100" data-testid={`admin-role-select-${row.user_key}`}>
                            <option value="owner">Owner</option><option value="sub_admin">Sub-Admin</option><option value="user">User</option>
                          </select>
                        ) : <span>{row.role}</span>}
                      </TableCell>
                      <TableCell>
                        <Input type="number" min="0" value={creditEdit[row.user_key] ?? row.credits} onChange={(e) => setCreditEdit((prev) => ({ ...prev, [row.user_key]: Number(e.target.value) }))} className="h-8 w-24 border-slate-700 bg-slate-900 text-slate-100" data-testid={`admin-credit-input-${row.user_key}`} />
                      </TableCell>
                      <TableCell>
                        {row.role === "sub_admin" ? (
                          <div className="flex items-center gap-2">
                            <Input type="number" min="1" value={quotaEdit[row.user_key] ?? row.quota_limit} onChange={(e) => setQuotaEdit((prev) => ({ ...prev, [row.user_key]: Number(e.target.value) }))} className="h-8 w-24 border-slate-700 bg-slate-900 text-slate-100" data-testid={`admin-quota-input-${row.user_key}`} disabled={!isOwner} />
                            <span className="text-xs text-slate-400">used {row.quota_used}</span>
                          </div>
                        ) : <span className="text-xs text-slate-500">-</span>}
                      </TableCell>
                      <TableCell className="text-xs text-slate-400">{row.created_by}</TableCell>
                      <TableCell className="space-x-2">
                        <Button type="button" onClick={() => updateCredits(row.user_key)} className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700" data-testid={`admin-update-credit-${row.user_key}`}>Update Credits</Button>
                        {isOwner && row.role === "sub_admin" ? <Button type="button" onClick={() => updateQuota(row.user_key)} className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700" data-testid={`admin-update-quota-${row.user_key}`}>Update Quota</Button> : null}
                        {isOwner ? (
                          <Button type="button" onClick={() => updateUserProfile(row.user_key)} className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700" data-testid={`admin-update-profile-${row.user_key}`}>Update Profile</Button>
                        ) : row.user_key === me?.user_key ? (
                          <Button type="button" onClick={updateOwnUsername} className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700" data-testid={`admin-update-own-username-${row.user_key}`}>Update My Login</Button>
                        ) : null}
                        {row.role !== "owner" ? (
                          <Button type="button" onClick={() => deleteUser(row.user_key)} className="h-8 border border-rose-600 bg-transparent px-3 text-xs text-rose-300 hover:bg-rose-500/10" data-testid={`admin-delete-${row.user_key}`}>Delete</Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {/* Advanced Controls */}
      {activeTab === "controls" && isOwner ? (
        <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-advanced-controls-card">
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
            <CardTitle className="text-white">Advanced Controls</CardTitle>
            <Button type="button" onClick={loadAdminConfig} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-refresh-config-button">Refresh Controls</Button>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-kite-enabled">
                <input type="checkbox" checked={Boolean(apiControlsEdit.kite_data_enabled)} onChange={(e) => setApiControlsEdit((prev) => ({ ...prev, kite_data_enabled: e.target.checked }))} /> Kite data enabled
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-moneycontrol-enabled">
                <input type="checkbox" checked={Boolean(apiControlsEdit.moneycontrol_data_enabled)} onChange={(e) => setApiControlsEdit((prev) => ({ ...prev, moneycontrol_data_enabled: e.target.checked }))} /> Secondary API enabled
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-strict-live-only">
                <input type="checkbox" checked={Boolean(apiControlsEdit.strict_live_only)} onChange={(e) => setApiControlsEdit((prev) => ({ ...prev, strict_live_only: e.target.checked }))} /> Strict live-only mode
              </label>
            </div>
            <Button type="button" onClick={saveApiControls} className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-save-api-controls">Save API Controls</Button>

            <form onSubmit={addDomainMapping} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="admin-domain-form">
              <Input value={domainForm.domain} onChange={(e) => setDomainForm((prev) => ({ ...prev, domain: e.target.value }))} placeholder="Domain or Subdomain (example.com / trade.example.com)" className="border-slate-700 bg-slate-900 text-slate-100" data-testid="admin-domain-input" />
              <Input value={domainForm.target_record} onChange={(e) => setDomainForm((prev) => ({ ...prev, target_record: e.target.value }))} placeholder="A-Record target (IP/host)" className="border-slate-700 bg-slate-900 text-slate-100" data-testid="admin-domain-target-input" />
              <Button type="submit" className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-domain-submit">Save Domain Mapping</Button>
            </form>

            {adminConfig?.hosting_dns_reference ? (
              <div className="rounded-md border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300" data-testid="admin-hosting-dns-reference">
                <p>Hosting Domain: <span className="font-mono text-cyan-300">{adminConfig.hosting_dns_reference.hosting_domain || "-"}</span></p>
                <p>Resolved IPv4: <span className="font-mono text-cyan-300">{adminConfig.hosting_dns_reference.resolved_ipv4 || "Unavailable"}</span></p>
                <p>Record Type: <span className="font-mono text-cyan-300">A</span></p>
                <p>Apex Host Label: <span className="font-mono text-cyan-300">@</span> | Subdomain Host Label Example: <span className="font-mono text-cyan-300">trade</span></p>
              </div>
            ) : null}
            <p className="text-xs text-slate-400" data-testid="admin-dns-note">{adminConfig?.dns_note || "A-record update must be done in your registrar DNS settings."}</p>
            {(adminConfig?.dns_instructions || []).length ? (
              <ul className="list-disc space-y-1 pl-5 text-xs text-slate-300" data-testid="admin-dns-instructions-list">
                {(adminConfig?.dns_instructions || []).map((step, idx) => <li key={`dns-step-${idx}`}>{step}</li>)}
              </ul>
            ) : null}

            <div className="space-y-3" data-testid="admin-domain-list">
              {(adminConfig?.domain_mappings || []).length === 0 && <p className="text-xs text-slate-500">No domain mappings yet. Add one above.</p>}
              {(adminConfig?.domain_mappings || []).map((row) => {
                const mapInfo = domainMapStatus[row.domain];
                const statusColor = row.status === "ACTIVE" ? "bg-emerald-600" : row.status === "PENDING_DNS" || row.status === "NGINX_CONFIG_GENERATED" ? "bg-yellow-600" : row.status === "FAILED" ? "bg-rose-600" : "bg-slate-600";
                return (
                  <div key={row.domain} className="rounded-lg border border-slate-700 bg-slate-900/80 p-3 space-y-2" data-testid={`admin-domain-card-${row.domain}`}>
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="space-y-0.5 text-xs"><p className="font-mono font-semibold text-cyan-300">{row.domain}</p><p className="text-slate-400">A Record: {row.resolved_target_ip || row.target_record || "\u2014"}</p></div>
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold text-white ${statusColor}`}>{row.status}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" size="sm" onClick={() => mapDomain(row.domain)} disabled={mapInfo?.loading} className="h-7 bg-cyan-700 px-3 text-xs text-white hover:bg-cyan-600" data-testid={`admin-domain-map-${row.domain}`}>{mapInfo?.loading ? "Mapping\u2026" : "MAP"}</Button>
                      <Button type="button" size="sm" onClick={() => updateDomainStatus(row.domain, "ACTIVE")} className="h-7 bg-emerald-700 px-3 text-xs text-white hover:bg-emerald-600" data-testid={`admin-domain-active-${row.domain}`}>Mark Active</Button>
                      <Button type="button" size="sm" onClick={() => setExpandedDnsInstructions((prev) => ({ ...prev, [row.domain]: !prev[row.domain] }))} className="h-7 bg-slate-700 px-3 text-xs text-white hover:bg-slate-600" data-testid={`admin-domain-dns-toggle-${row.domain}`}>{expandedDnsInstructions[row.domain] ? "Hide DNS" : "DNS Instructions"}</Button>
                      <Button type="button" size="sm" onClick={() => setDomainDeleteConfirm(row.domain)} className="h-7 bg-rose-700 px-3 text-xs text-white hover:bg-rose-600" data-testid={`admin-domain-delete-${row.domain}`}>Delete</Button>
                    </div>
                    {expandedDnsInstructions[row.domain] && (
                      <div className="rounded-md border border-slate-700 bg-slate-950 p-3 text-xs text-slate-300 space-y-1" data-testid={`admin-domain-dns-${row.domain}`}>
                        <p className="font-semibold text-cyan-300 mb-1">DNS Setup Instructions</p>
                        <p>1. Open your domain registrar / DNS provider</p>
                        <p>2. Add an <strong>A Record</strong>: Host = <code className="text-yellow-300">{row.host_label || "@"}</code>, Value = <code className="text-yellow-300">{row.resolved_target_ip || row.target_record || "[server IP]"}</code>, TTL = 300</p>
                        <p>3. Delete any conflicting A record for the same host label</p>
                        <p>4. Wait 5\u201330 minutes for propagation</p>
                        <p>5. After DNS resolves, click <strong>MAP</strong> above to configure the server proxy</p>
                      </div>
                    )}
                    {mapInfo?.result && (
                      <div className={`rounded-md p-2 text-xs ${mapInfo.result.error ? "bg-rose-900/40 text-rose-300" : "bg-emerald-900/40 text-emerald-300"}`} data-testid={`admin-domain-map-result-${row.domain}`}>
                        {mapInfo.result.error ? `Map error: ${mapInfo.result.error}` : `Mapped (${mapInfo.result.nginx_status}) \u2014 DNS must point to server IP`}
                      </div>
                    )}
                    {domainDeleteConfirm === row.domain && (
                      <div className="rounded-md border border-rose-700 bg-rose-950/60 p-3 text-xs space-y-2" data-testid={`admin-domain-delete-confirm-${row.domain}`}>
                        <p className="text-rose-300 font-semibold">Confirm delete domain mapping: <span className="font-mono">{row.domain}</span>?</p>
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => deleteDomainMapping(row.domain)} className="h-7 bg-rose-600 px-3 text-xs text-white hover:bg-rose-500" data-testid="admin-domain-delete-confirm-yes">Yes, Delete</Button>
                          <Button size="sm" onClick={() => setDomainDeleteConfirm(null)} className="h-7 bg-slate-700 px-3 text-xs text-white hover:bg-slate-600" data-testid="admin-domain-delete-confirm-no">Cancel</Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Macro Events */}
      {activeTab === "macro" && isOwner && (
        <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-macro-events-card">
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
            <div>
              <CardTitle className="text-white">Active Macro Events</CardTitle>
              <p className="mt-1 text-xs text-slate-400">Toggle events to influence sector macro bias in F&amp;O signals and Multibagger analysis. Changes apply instantly.</p>
            </div>
            <div className="flex items-center gap-2">
              {macroEventsSaving && <span className="text-xs text-cyan-400" data-testid="macro-events-saving">Saving\u2026</span>}
              <Button type="button" onClick={loadMacroEvents} className="bg-slate-800 text-slate-100 hover:bg-slate-700 h-8 px-3 text-xs" data-testid="admin-macro-events-refresh">Refresh</Button>
            </div>
          </CardHeader>
          <CardContent>
            {macroEventsData.active_events.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1.5" data-testid="macro-events-active-summary">
                <span className="text-xs text-slate-500">Active:</span>
                {macroEventsData.active_events.map((key) => <span key={key} className="rounded-full bg-cyan-900/60 px-2 py-0.5 text-xs font-medium text-cyan-300 border border-cyan-700/50">{key}</span>)}
              </div>
            )}
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="macro-events-grid">
              {(macroEventsData.all_events || []).map((event) => {
                const isActive = macroEventsData.active_events.includes(event.key);
                const intensityColor = { CRITICAL: "text-rose-400 border-rose-700/60 bg-rose-950/40", HIGH: "text-orange-400 border-orange-700/60 bg-orange-950/40", MEDIUM: "text-yellow-400 border-yellow-700/60 bg-yellow-950/40", LOW: "text-slate-400 border-slate-700/60 bg-slate-900/40" }[event.intensity] || "text-slate-400 border-slate-700/60 bg-slate-900/40";
                return (
                  <button key={event.key} type="button" data-testid={`macro-event-toggle-${event.key}`} onClick={() => toggleMacroEvent(event.key)}
                    className={`flex items-start justify-between rounded-lg border p-2.5 text-left transition-all ${isActive ? "border-cyan-500 bg-cyan-900/30 ring-1 ring-cyan-500/40" : "border-slate-700 bg-slate-900/60 hover:border-slate-600"}`}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`text-xs font-semibold ${isActive ? "text-cyan-300" : "text-slate-300"}`}>{event.key}</span>
                        <span className={`rounded px-1 py-px text-[10px] font-medium border ${intensityColor}`}>{event.intensity}</span>
                      </div>
                      {event.description && <p className="mt-0.5 text-[11px] text-slate-500 leading-tight line-clamp-2">{event.description}</p>}
                      {event.beneficiaries?.length > 0 && <p className="mt-0.5 text-[10px] text-emerald-500/80">+ {event.beneficiaries.slice(0, 3).join(", ")}</p>}
                    </div>
                    <div className={`ml-2 mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 transition-colors ${isActive ? "border-cyan-400 bg-cyan-400" : "border-slate-600 bg-transparent"}`} />
                  </button>
                );
              })}
            </div>
            {macroEventsData.all_events.length === 0 && <p className="text-xs text-slate-500" data-testid="macro-events-empty">No events loaded. Click Refresh to load.</p>}
          </CardContent>
        </Card>
      )}

      {/* Kite Connect */}
      {activeTab === "kite" && isOwner && (
        <Card className="result-card border-slate-800 bg-slate-950/70">
          <CardHeader><CardTitle className="text-white">Kite Connect Integration</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-4">
              <div className="space-y-2">
                <p className="text-sm font-semibold text-slate-200">Connection Status</p>
                <div className="flex items-center gap-2">
                  {kiteStatus?.connected ? (
                    <><span className="inline-block h-3 w-3 rounded-full bg-green-500"></span><span className="text-sm text-green-400">{"\u2705"} Connected</span><span className="text-xs text-slate-400">| User: {kiteStatus.user_id}</span></>
                  ) : (
                    <><span className="inline-block h-3 w-3 rounded-full bg-red-500"></span><span className="text-sm text-red-400">{"\u274c"} Disconnected</span></>
                  )}
                </div>
                {kiteStatus?.date && <p className="text-xs text-slate-500">Last authenticated: {kiteStatus.date}</p>}
              </div>
              <Button type="button" onClick={async () => {
                try { const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/kite/auth-url`, { headers: { Authorization: `Bearer ${token}` } }); const data = await res.json(); if (data.auth_url) { window.open(data.auth_url, '_blank'); setTimeout(() => checkKiteStatus(), 3000); } } catch (err) { console.error('Kite auth error:', err); }
              }} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400">Connect Kite</Button>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
              <p className="text-xs font-semibold text-slate-300 mb-2">OAuth URL:</p>
              <p className="text-xs text-cyan-400 break-all font-mono">https://kite.zerodha.com/connect/login?v=3&api_key=wgbgees3zbjpn254</p>
              <p className="text-xs text-slate-500 mt-2">Note: Kite authentication expires daily. Re-authenticate each trading day for live data.</p>
            </div>
            <Button type="button" onClick={checkKiteStatus} className="bg-slate-800 text-slate-100 hover:bg-slate-700">Refresh Status</Button>
          </CardContent>
        </Card>
      )}

      {/* CSV Seed Management */}
      {activeTab === "csv" && (
      <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="csv-seed-card">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <CardTitle className="text-white">OHLCV CSV Seed Management</CardTitle>
          <Button type="button" onClick={loadCsvSeeds} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="csv-seed-refresh-btn">Refresh Seeds</Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200" data-testid="csv-seed-guide">
            <p className="font-semibold mb-1">Admin Guide: CSV Seed Files</p>
            <ul className="list-disc pl-4 space-y-0.5">
              <li>Upload verified CSV files with columns: <code className="bg-slate-800 px-1 rounded">date,open,high,low,close,volume</code></li>
              <li>Files are named by symbol (e.g., NIFTY.csv, RELIANCE.csv)</li>
              <li>Used ONLY when Kite Connect is unavailable (offline fallback)</li>
              <li>Data must be manually verified before upload — no auto-scraping</li>
              <li>Primary source is always Kite Connect Historical Data API</li>
            </ul>
          </div>
          <form onSubmit={uploadCsvSeed} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="csv-seed-upload-form">
            <Input value={csvUploadSymbol} onChange={(e) => setCsvUploadSymbol(e.target.value)} placeholder="Symbol (e.g., NIFTY)" className="border-slate-700 bg-slate-900 text-slate-100" data-testid="csv-seed-symbol-input" />
            <input type="file" accept=".csv" className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-cyan-500/20 file:px-2 file:py-1 file:text-xs file:text-cyan-300" data-testid="csv-seed-file-input" />
            <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" disabled={csvSeedLoading} data-testid="csv-seed-upload-btn">Upload CSV</Button>
          </form>
          {csvSeedMsg ? <p className="text-sm text-cyan-300" data-testid="csv-seed-msg">{csvSeedMsg}</p> : null}
          {csvSeedLoading ? (
            <p className="text-sm text-slate-400">Loading...</p>
          ) : csvSeeds.length > 0 ? (
            <div className="relative w-full overflow-auto rounded-lg border border-slate-800">
              <Table data-testid="csv-seed-table">
                <TableHeader>
                  <TableRow className="border-slate-800 hover:bg-slate-900/50">
                    <TableHead className="text-slate-400">Symbol</TableHead><TableHead className="text-slate-400">File</TableHead><TableHead className="text-right text-slate-400">Rows</TableHead><TableHead className="text-right text-slate-400">Size (KB)</TableHead><TableHead className="text-right text-slate-400">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {csvSeeds.map((seed) => (
                    <TableRow key={seed.symbol} className="border-slate-800 hover:bg-slate-900/50">
                      <TableCell className="font-medium text-white">{seed.symbol}</TableCell>
                      <TableCell className="text-slate-300">{seed.file}</TableCell>
                      <TableCell className="text-right text-slate-300">{seed.rows}</TableCell>
                      <TableCell className="text-right text-slate-300">{seed.size_kb}</TableCell>
                      <TableCell className="text-right">
                        <Button type="button" onClick={() => deleteCsvSeed(seed.symbol)} className="bg-rose-500/20 text-rose-300 hover:bg-rose-500/40 text-xs h-7 px-2" data-testid={`csv-seed-delete-${seed.symbol}`}>Delete</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <p className="text-sm text-slate-500" data-testid="csv-seed-empty">No CSV seeds uploaded. Backtests will use Kite Connect data only.</p>
          )}
        </CardContent>
      </Card>
      )}
    </section>
  );
}
