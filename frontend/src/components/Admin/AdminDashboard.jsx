import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { SubTabs } from "@/components/Layout/SubTabs";
import { AdminUsersTab } from "./AdminUsersTab";
import { AdminApiTab } from "./AdminApiTab";
import { AdminCsvTab } from "./AdminCsvTab";
import { AdminPerfTab } from "./AdminPerfTab";
import { AdminControlsTab } from "./AdminControlsTab";
import { AdminMacroTab } from "./AdminMacroTab";
import { AdminCrmPanel, AdminFraudPanel, AdminPermissionsPanel } from "./AdminCrmPanel";
import { AdminPaymentsPanel } from "./AdminPaymentsPanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ADMIN_TABS = [
  { id: "users", label: "User Management" },
  { id: "permissions", label: "Permissions & Packages" },
  { id: "payments", label: "Payments" },
  { id: "crm", label: "CRM Messages" },
  { id: "fraud", label: "Fraud Detection" },
  { id: "controls", label: "Advanced Controls" },
  { id: "macro", label: "Active Macro Events" },
  { id: "perf", label: "Generation Performance" },
  { id: "kite", label: "API Connect" },
  { id: "csv", label: "CSV Seeds" },
];

export function AdminDashboard({ authHeaders, me, isAdmin, isOwner, token, hydrateMe }) {
  const [activeTab, setActiveTab] = useState("users");
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminError, setAdminError] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminConfig, setAdminConfig] = useState(null);
  const [kiteStatus, setKiteStatus] = useState(null);

  // User editing state
  const [createForm, setCreateForm] = useState({ username: "", role: "user", initial_credits: 0, quota_limit: 10 });
  const [usernameEdit, setUsernameEdit] = useState({});
  const [roleEdit, setRoleEdit] = useState({});
  const [creditEdit, setCreditEdit] = useState({});
  const [quotaEdit, setQuotaEdit] = useState({});

  // CSV state
  const [csvSeeds, setCsvSeeds] = useState([]);
  const [csvSeedLoading, setCsvSeedLoading] = useState(false);
  const [csvSeedMsg, setCsvSeedMsg] = useState("");
  const [csvUploadSymbol, setCsvUploadSymbol] = useState("");

  const checkKiteStatus = useCallback(async () => {
    try { const r = await axios.get(`${API}/kite/status`, { headers: authHeaders }); setKiteStatus(r.data); }
    catch { setKiteStatus({ connected: false }); }
  }, [authHeaders]);

  const loadAdminUsers = useCallback(async () => {
    setAdminLoading(true); setAdminError("");
    try {
      const r = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      const rows = r.data || [];
      setAdminUsers(rows);
      const cm = {}, qm = {}, um = {}, rm = {};
      rows.forEach(row => { cm[row.user_key] = row.credits; qm[row.user_key] = row.quota_limit; um[row.user_key] = row.username; rm[row.user_key] = row.role; });
      setCreditEdit(cm); setQuotaEdit(qm); setUsernameEdit(um); setRoleEdit(rm);
    } catch (e) { setAdminError(e?.response?.data?.detail || "Unable to load users"); }
    finally { setAdminLoading(false); }
  }, [authHeaders]);

  const loadAdminConfig = useCallback(async () => {
    try { const r = await axios.get(`${API}/admin/config`, { headers: authHeaders }); setAdminConfig(r.data); }
    catch (e) { setAdminError(e?.response?.data?.detail || "Unable to load admin config"); }
  }, [authHeaders]);

  useEffect(() => {
    loadAdminUsers();
    if (isOwner) loadAdminConfig();
    checkKiteStatus();
  }, [loadAdminUsers, loadAdminConfig, checkKiteStatus, isOwner]);

  // User CRUD actions
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

  // CSV actions
  const loadCsvSeeds = useCallback(async () => {
    setCsvSeedLoading(true); setCsvSeedMsg("");
    try { const r = await axios.get(`${API}/admin/csv-seeds`, { headers: authHeaders }); setCsvSeeds(r.data.seeds || []); }
    catch (e) { setCsvSeedMsg(e?.response?.data?.detail || "Unable to load CSV seeds"); }
    setCsvSeedLoading(false);
  }, [authHeaders]);

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

      {activeTab === "users" && (
        <AdminUsersTab
          adminUsers={adminUsers} adminError={adminError} adminLoading={adminLoading}
          isOwner={isOwner} me={me}
          createForm={createForm} setCreateForm={setCreateForm}
          usernameEdit={usernameEdit} setUsernameEdit={setUsernameEdit}
          roleEdit={roleEdit} setRoleEdit={setRoleEdit}
          creditEdit={creditEdit} setCreditEdit={setCreditEdit}
          quotaEdit={quotaEdit} setQuotaEdit={setQuotaEdit}
          loadAdminUsers={loadAdminUsers} createUser={createUser}
          updateCredits={updateCredits} updateQuota={updateQuota}
          updateUserProfile={updateUserProfile} updateOwnUsername={updateOwnUsername}
          deleteUser={deleteUser}
        />
      )}

      {activeTab === "permissions" && isOwner && <AdminPermissionsPanel authHeaders={authHeaders} />}
      {activeTab === "payments" && isOwner && <AdminPaymentsPanel authHeaders={authHeaders} />}
      {activeTab === "crm" && <AdminCrmPanel authHeaders={authHeaders} />}
      {activeTab === "fraud" && <AdminFraudPanel authHeaders={authHeaders} />}
      {activeTab === "controls" && isOwner && <AdminControlsTab authHeaders={authHeaders} adminConfig={adminConfig} loadAdminConfig={loadAdminConfig} adminError={adminError} setAdminError={setAdminError} />}
      {activeTab === "macro" && isOwner && <AdminMacroTab authHeaders={authHeaders} />}
      {activeTab === "kite" && isOwner && <AdminApiTab kiteStatus={kiteStatus} checkKiteStatus={checkKiteStatus} token={token} />}
      {activeTab === "perf" && isOwner && <AdminPerfTab authHeaders={authHeaders} />}
      {activeTab === "csv" && (
        <AdminCsvTab
          csvSeeds={csvSeeds} csvSeedLoading={csvSeedLoading} csvSeedMsg={csvSeedMsg}
          csvUploadSymbol={csvUploadSymbol} setCsvUploadSymbol={setCsvUploadSymbol}
          loadCsvSeeds={loadCsvSeeds} uploadCsvSeed={uploadCsvSeed} deleteCsvSeed={deleteCsvSeed}
        />
      )}
    </section>
  );
}
