import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CreditCard, Check, X, Eye, Image, Settings, History } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function AdminPaymentsPanel({ authHeaders }) {
  const [configStatus, setConfigStatus] = useState(null);
  const [pending, setPending] = useState([]);
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [showConfig, setShowConfig] = useState(false);
  const [configForm, setConfigForm] = useState({ key_id: "", key_secret: "", upi_id: "" });
  const [proofImage, setProofImage] = useState(null);
  const [proofPaymentId, setProofPaymentId] = useState(null);
  const [tab, setTab] = useState("pending");

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/payments/config-status`, { headers: authHeaders });
      setConfigStatus(res.data);
    } catch (err) { console.error("Failed to fetch payment config:", err?.message); }
  }, [authHeaders]);

  const fetchPending = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/payments/pending`, { headers: authHeaders });
      setPending(res.data.payments || []);
    } catch (err) { console.error("Failed to fetch pending payments:", err?.message); }
  }, [authHeaders]);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/payments/history?limit=100`, { headers: authHeaders });
      setHistory(res.data.payments || []);
      setHistoryTotal(res.data.total || 0);
    } catch (err) { console.error("Failed to fetch payment history:", err?.message); }
  }, [authHeaders]);

  useEffect(() => { fetchStatus(); fetchPending(); fetchHistory(); }, [fetchStatus, fetchPending, fetchHistory]);

  const saveConfig = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/admin/payments/configure`, configForm, { headers: authHeaders });
      setShowConfig(false);
      fetchStatus();
    } catch (err) { console.error(err); }
  };

  const verifyPayment = async (paymentId, action) => {
    try {
      await axios.post(`${API}/admin/payments/${paymentId}/verify?action=${action}`, {}, { headers: authHeaders });
      fetchPending();
      fetchHistory();
    } catch (err) { console.error(err); }
  };

  const viewProof = async (paymentId) => {
    try {
      const res = await axios.get(`${API}/admin/payments/${paymentId}/proof`, { headers: authHeaders });
      setProofImage(res.data.proof_image);
      setProofPaymentId(paymentId);
    } catch (err) { console.error(err); }
  };

  const statusColor = (s) => {
    if (s === "verified" || s === "approved") return "text-emerald-400 bg-emerald-950/30";
    if (s === "rejected") return "text-rose-400 bg-rose-950/30";
    if (s === "pending_verification") return "text-amber-400 bg-amber-950/30";
    return "text-slate-400 bg-slate-800";
  };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="admin-payments-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2">
          <CreditCard size={16} className="text-emerald-400" /> Payment Management
        </CardTitle>
        <div className="flex gap-2">
          <Button onClick={() => setShowConfig(!showConfig)} className="h-7 bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs px-3" data-testid="payments-config-toggle">
            <Settings size={12} className="mr-1" /> Configure
          </Button>
          <Button onClick={() => { fetchPending(); fetchHistory(); }} className="h-7 bg-emerald-600 text-white hover:bg-emerald-500 text-xs px-3" data-testid="payments-refresh">Refresh</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Config Status */}
        <div className="flex gap-3 text-[10px] flex-wrap" data-testid="payments-status">
          <span className={configStatus?.razorpay_configured ? "text-emerald-400" : "text-slate-500"}>
            Razorpay: {configStatus?.razorpay_configured ? "Configured" : "Not Set"}
          </span>
          <span className={configStatus?.razorpay_enabled ? "text-emerald-400" : "text-rose-400"}>
            Online: {configStatus?.razorpay_enabled ? "Enabled" : "Disabled"}
          </span>
          <span className={configStatus?.upi_configured ? "text-emerald-400" : "text-slate-500"}>
            UPI QR: {configStatus?.upi_configured ? "Configured" : "Not Set"}
          </span>
          <span className={configStatus?.offline_enabled ? "text-emerald-400" : "text-rose-400"}>
            Offline: {configStatus?.offline_enabled ? "Enabled" : "Disabled"}
          </span>
          {configStatus?.has_qr_image && <span className="text-cyan-400">QR Image: Uploaded</span>}
        </div>

        {showConfig && (
          <form onSubmit={saveConfig} className="space-y-2 rounded-lg border border-slate-700 bg-slate-900/50 p-3" data-testid="payments-config-form">
            <p className="text-[10px] text-slate-400 font-semibold">Payment Mode Toggles</p>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={configForm.razorpay_enabled ?? true} onChange={(e) => setConfigForm(p => ({ ...p, razorpay_enabled: e.target.checked }))} className="accent-emerald-500" data-testid="payments-toggle-razorpay" />
                Razorpay Online
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={configForm.offline_enabled ?? true} onChange={(e) => setConfigForm(p => ({ ...p, offline_enabled: e.target.checked }))} className="accent-emerald-500" data-testid="payments-toggle-offline" />
                Offline UPI/QR
              </label>
            </div>
            <p className="text-[10px] text-slate-400 font-semibold">Razorpay Credentials</p>
            <Input value={configForm.key_id} onChange={(e) => setConfigForm(p => ({ ...p, key_id: e.target.value }))} placeholder="Razorpay Key ID (rzp_...)" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="payments-key-id" />
            <Input type="password" value={configForm.key_secret} onChange={(e) => setConfigForm(p => ({ ...p, key_secret: e.target.value }))} placeholder="Razorpay Key Secret" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="payments-key-secret" />
            <p className="text-[10px] text-slate-400 font-semibold mt-2">UPI for QR Code (Offline Payments)</p>
            <Input value={configForm.upi_id} onChange={(e) => setConfigForm(p => ({ ...p, upi_id: e.target.value }))} placeholder="UPI ID (e.g. merchant@paytm)" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="payments-upi-id" />
            <p className="text-[10px] text-slate-400 font-semibold mt-2">Upload Custom QR Image</p>
            <input type="file" accept="image/*" onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                const reader = new FileReader();
                reader.onload = (ev) => setConfigForm(p => ({ ...p, qr_image_base64: ev.target.result }));
                reader.readAsDataURL(file);
              }
            }} className="text-xs text-slate-400" data-testid="payments-qr-upload" />
            {configForm.qr_image_base64 && <img src={configForm.qr_image_base64} alt="QR Preview" className="w-24 h-24 rounded border border-slate-700" />}
            <Button type="submit" className="h-7 bg-emerald-600 text-white hover:bg-emerald-500 text-xs" data-testid="payments-config-save">Save Configuration</Button>
          </form>
        )}

        {/* Tabs: Pending | History */}
        <div className="flex gap-2 border-b border-slate-800 pb-2">
          <button onClick={() => setTab("pending")} className={`text-xs px-3 py-1 rounded ${tab === "pending" ? "bg-amber-600 text-white" : "text-slate-400"}`} data-testid="payments-tab-pending">
            Pending ({pending.length})
          </button>
          <button onClick={() => setTab("history")} className={`text-xs px-3 py-1 rounded flex items-center gap-1 ${tab === "history" ? "bg-emerald-600 text-white" : "text-slate-400"}`} data-testid="payments-tab-history">
            <History size={12} /> History ({historyTotal})
          </button>
        </div>

        {/* Pending Payments */}
        {tab === "pending" && (
          <div>
            <p className="text-[10px] text-slate-400 font-semibold mb-1.5">Pending Verifications ({pending.length})</p>
            {pending.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-3">No pending payments</p>
            ) : (
              <div className="space-y-1.5" data-testid="pending-payments-list">
                {pending.map(p => (
                  <div key={p.payment_id} className="rounded-lg border border-amber-500/30 bg-amber-950/20 px-3 py-2" data-testid={`payment-${p.payment_id}`}>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <span className="text-xs font-bold text-white">{p.username}</span>
                        <span className="ml-2 text-[10px] text-amber-300">INR {p.amount}</span>
                        <span className="ml-2 text-[10px] text-slate-500">{p.method}</span>
                        {p.notes && <p className="text-[10px] text-slate-400 mt-0.5">{p.notes}</p>}
                        <span className="text-[9px] text-slate-600 block">{p.created_at ? new Date(p.created_at).toLocaleString("en-IN") : ""}</span>
                      </div>
                      <div className="flex gap-1">
                        <button onClick={() => viewProof(p.payment_id)} className="p-1 text-cyan-400 hover:text-cyan-300" title="View Proof" data-testid={`proof-${p.payment_id}`}><Image size={14} /></button>
                        <button onClick={() => verifyPayment(p.payment_id, "approve")} className="p-1 text-emerald-400 hover:text-emerald-300" title="Approve" data-testid={`approve-${p.payment_id}`}><Check size={14} /></button>
                        <button onClick={() => verifyPayment(p.payment_id, "reject")} className="p-1 text-rose-400 hover:text-rose-300" title="Reject" data-testid={`reject-${p.payment_id}`}><X size={14} /></button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Payment History */}
        {tab === "history" && (
          <div data-testid="payment-history-list">
            {history.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-3">No payment history yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[10px]" data-testid="payment-history-table">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-700">
                      <th className="px-2 py-1.5 text-left">User</th>
                      <th className="px-2 py-1.5 text-right">Amount</th>
                      <th className="px-2 py-1.5 text-center">Method</th>
                      <th className="px-2 py-1.5 text-center">Status</th>
                      <th className="px-2 py-1.5 text-left">Purpose</th>
                      <th className="px-2 py-1.5 text-right">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map(p => (
                      <tr key={p.payment_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td className="px-2 py-1.5 text-slate-200 font-semibold">{p.username}</td>
                        <td className="px-2 py-1.5 text-right text-slate-200 font-mono">INR {p.amount || 0}</td>
                        <td className="px-2 py-1.5 text-center text-slate-400">{p.method || "—"}</td>
                        <td className="px-2 py-1.5 text-center">
                          <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${statusColor(p.status)}`}>{(p.status || "").replace(/_/g, " ")}</span>
                        </td>
                        <td className="px-2 py-1.5 text-slate-400">{p.purpose || "reactivation"}</td>
                        <td className="px-2 py-1.5 text-right text-slate-500">{p.created_at ? new Date(p.created_at).toLocaleDateString("en-IN") : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Proof Image Modal */}
        {proofImage && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={() => { setProofImage(null); setProofPaymentId(null); }} data-testid="proof-modal">
            <div className="bg-slate-950 rounded-xl p-4 max-w-lg max-h-[80vh] overflow-auto border border-slate-700" onClick={e => e.stopPropagation()}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-white font-bold">Payment Proof</span>
                <button onClick={() => { setProofImage(null); setProofPaymentId(null); }} className="text-slate-400 hover:text-white"><X size={16} /></button>
              </div>
              <img src={proofImage} alt="Payment proof" className="w-full rounded-lg" />
              <div className="flex gap-2 mt-3">
                <Button onClick={() => { verifyPayment(proofPaymentId, "approve"); setProofImage(null); }} className="h-7 bg-emerald-600 text-white text-xs flex-1" data-testid="proof-approve">Approve & Reactivate</Button>
                <Button onClick={() => { verifyPayment(proofPaymentId, "reject"); setProofImage(null); }} className="h-7 bg-rose-600 text-white text-xs flex-1" data-testid="proof-reject">Reject</Button>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
