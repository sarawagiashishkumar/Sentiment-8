import { useState, useCallback } from "react";
import { Button } from "components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { Input } from "components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "components/ui/table";
import { UserCog, Download, Ban, CheckCircle, PlusCircle, CreditCard } from "lucide-react";
import axios from "axios";

const API = "/api";

const roles = [
  { value: "user", label: "Basic User" },
  { value: "sub_admin", label: "Sub-Admin" },
];

export function AdminUsersTab({
  adminUsers, adminError, adminLoading, isOwner, me,
  createForm, setCreateForm, usernameEdit, setUsernameEdit,
  roleEdit, setRoleEdit, creditEdit, setCreditEdit,
  quotaEdit, setQuotaEdit,
  loadAdminUsers, createUser, updateCredits, updateQuota,
  updateUserProfile, updateOwnUsername, deleteUser, authHeaders,
}) {
  const [selected, setSelected] = useState(new Set());
  const [bulkCredits, setBulkCredits] = useState("");
  const [showBulk, setShowBulk] = useState(false);
  const [topupUser, setTopupUser] = useState(null);
  const [topupAmount, setTopupAmount] = useState("");

  const toggleSelect = (userKey) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(userKey) ? next.delete(userKey) : next.add(userKey);
      return next;
    });
  };

  const selectAll = () => {
    if (selected.size === adminUsers.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(adminUsers.map(u => u.user_key)));
    }
  };

  const suspendUser = useCallback(async (userRef) => {
    try {
      await axios.post(`${API}/admin/users/${userRef}/suspend`, {}, { headers: authHeaders });
      await loadAdminUsers();
    } catch (e) { console.error("Suspend failed:", e?.message); }
  }, [authHeaders, loadAdminUsers]);

  const topupCredits = useCallback(async () => {
    if (!topupUser || !topupAmount || Number(topupAmount) <= 0) return;
    try {
      await axios.post(`${API}/admin/users/${topupUser}/topup`, { credits: Number(topupAmount) }, { headers: authHeaders });
      setTopupUser(null);
      setTopupAmount("");
      await loadAdminUsers();
    } catch (e) { console.error("Topup failed:", e?.message); }
  }, [authHeaders, topupUser, topupAmount, loadAdminUsers]);

  const bulkAdjust = useCallback(async () => {
    if (!bulkCredits || selected.size === 0) return;
    try {
      await axios.post(`${API}/admin/users/bulk-credits`, {
        user_keys: Array.from(selected),
        credits_delta: Number(bulkCredits),
      }, { headers: authHeaders });
      setBulkCredits("");
      setShowBulk(false);
      setSelected(new Set());
      await loadAdminUsers();
    } catch (e) { console.error("Bulk credit failed:", e?.message); }
  }, [authHeaders, bulkCredits, selected, loadAdminUsers]);

  const exportCsv = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/users/export`, { headers: authHeaders, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a"); a.href = url; a.download = "users_export.csv"; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { console.error("Export failed:", e?.message); }
  }, [authHeaders]);

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white">User Management & Security</CardTitle>
        <div className="flex gap-2 flex-wrap">
          {isOwner && (
            <Button type="button" onClick={exportCsv} variant="outline" className="h-8 border-cyan-700 bg-cyan-900/30 text-cyan-300 hover:bg-cyan-800/50 text-xs gap-1" data-testid="admin-export-users-btn">
              <Download size={14} /> Export CSV
            </Button>
          )}
          {isOwner && selected.size > 0 && (
            <Button type="button" onClick={() => setShowBulk(!showBulk)} variant="outline" className="h-8 border-amber-700 bg-amber-900/30 text-amber-300 hover:bg-amber-800/50 text-xs gap-1" data-testid="admin-bulk-btn">
              <CreditCard size={14} /> Bulk ({selected.size})
            </Button>
          )}
          <Button type="button" onClick={loadAdminUsers} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-refresh-users-button">
            <UserCog size={16} /> Refresh Users
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Bulk Credit Panel */}
        {showBulk && selected.size > 0 && (
          <div className="flex items-center gap-3 rounded-md border border-amber-700/40 bg-amber-950/20 p-3" data-testid="admin-bulk-panel">
            <span className="text-xs text-amber-300">{selected.size} users selected</span>
            <Input type="number" value={bulkCredits} onChange={(e) => setBulkCredits(e.target.value)} placeholder="Credits +/-" className="w-28 h-8 border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="admin-bulk-credits-input" />
            <Button type="button" onClick={bulkAdjust} className="h-8 bg-amber-600 text-white hover:bg-amber-500 text-xs" data-testid="admin-bulk-apply-btn">Apply</Button>
            <Button type="button" onClick={() => { setShowBulk(false); setSelected(new Set()); }} variant="ghost" className="h-8 text-xs text-slate-400">Cancel</Button>
          </div>
        )}

        {/* Topup inline */}
        {topupUser && (
          <div className="flex items-center gap-3 rounded-md border border-emerald-700/40 bg-emerald-950/20 p-3" data-testid="admin-topup-panel">
            <span className="text-xs text-emerald-300">Topup: {adminUsers.find(u => u.user_key === topupUser)?.username}</span>
            <Input type="number" min="1" value={topupAmount} onChange={(e) => setTopupAmount(e.target.value)} placeholder="Credits to add" className="w-28 h-8 border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="admin-topup-input" />
            <Button type="button" onClick={topupCredits} className="h-8 bg-emerald-600 text-white hover:bg-emerald-500 text-xs" data-testid="admin-topup-apply-btn">Add Credits</Button>
            <Button type="button" onClick={() => setTopupUser(null)} variant="ghost" className="h-8 text-xs text-slate-400">Cancel</Button>
          </div>
        )}

        {/* Create User Form */}
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
                  {isOwner && (
                    <TableHead className="w-8">
                      <input type="checkbox" checked={selected.size === adminUsers.length && adminUsers.length > 0} onChange={selectAll} className="accent-cyan-500" data-testid="admin-select-all" />
                    </TableHead>
                  )}
                  <TableHead>Credential</TableHead><TableHead>Role</TableHead><TableHead>Credits</TableHead><TableHead>Status</TableHead><TableHead>Quota</TableHead><TableHead>Created By</TableHead><TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {adminUsers.map((row) => (
                  <TableRow key={row.user_key} className={`result-row ${row.suspended ? "opacity-50" : ""}`} data-testid={`admin-row-${row.user_key}`}>
                    {isOwner && (
                      <TableCell>
                        <input type="checkbox" checked={selected.has(row.user_key)} onChange={() => toggleSelect(row.user_key)} className="accent-cyan-500" data-testid={`admin-select-${row.user_key}`} />
                      </TableCell>
                    )}
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
                      {row.suspended ? (
                        <span className="rounded bg-rose-500/20 px-2 py-0.5 text-[10px] text-rose-300 font-bold">SUSPENDED</span>
                      ) : (
                        <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">Active</span>
                      )}
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
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <Button type="button" onClick={() => updateCredits(row.user_key)} className="h-7 bg-slate-800 px-2 text-[10px] text-slate-100 hover:bg-slate-700" data-testid={`admin-update-credit-${row.user_key}`}>Set Cr</Button>
                        {row.role !== "owner" && (
                          <Button type="button" onClick={() => { setTopupUser(row.user_key); setTopupAmount(""); }} className="h-7 bg-emerald-800 px-2 text-[10px] text-emerald-200 hover:bg-emerald-700" data-testid={`admin-topup-btn-${row.user_key}`}>
                            <PlusCircle size={10} className="mr-0.5" /> Top-up
                          </Button>
                        )}
                        {isOwner && row.role === "sub_admin" ? <Button type="button" onClick={() => updateQuota(row.user_key)} className="h-7 bg-slate-800 px-2 text-[10px] text-slate-100 hover:bg-slate-700" data-testid={`admin-update-quota-${row.user_key}`}>Quota</Button> : null}
                        {isOwner ? (
                          <Button type="button" onClick={() => updateUserProfile(row.user_key)} className="h-7 bg-slate-800 px-2 text-[10px] text-slate-100 hover:bg-slate-700" data-testid={`admin-update-profile-${row.user_key}`}>Profile</Button>
                        ) : row.user_key === me?.user_key ? (
                          <Button type="button" onClick={updateOwnUsername} className="h-7 bg-slate-800 px-2 text-[10px] text-slate-100 hover:bg-slate-700" data-testid={`admin-update-own-username-${row.user_key}`}>My Login</Button>
                        ) : null}
                        {row.role !== "owner" && isOwner && (
                          <Button type="button" onClick={() => suspendUser(row.user_key)} className={`h-7 px-2 text-[10px] ${row.suspended ? "bg-emerald-800 text-emerald-200 hover:bg-emerald-700" : "bg-amber-800 text-amber-200 hover:bg-amber-700"}`} data-testid={`admin-suspend-${row.user_key}`}>
                            {row.suspended ? <><CheckCircle size={10} className="mr-0.5" /> Unsuspend</> : <><Ban size={10} className="mr-0.5" /> Suspend</>}
                          </Button>
                        )}
                        {row.role !== "owner" ? (
                          <Button type="button" onClick={() => deleteUser(row.user_key)} className="h-7 border border-rose-600 bg-transparent px-2 text-[10px] text-rose-300 hover:bg-rose-500/10" data-testid={`admin-delete-${row.user_key}`}>Delete</Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
