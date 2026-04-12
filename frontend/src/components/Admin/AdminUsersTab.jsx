import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { UserCog } from "lucide-react";

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
  updateUserProfile, updateOwnUsername, deleteUser,
}) {
  return (
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
  );
}
