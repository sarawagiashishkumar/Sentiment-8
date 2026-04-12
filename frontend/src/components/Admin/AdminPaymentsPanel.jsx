import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CreditCard, Check, X, Eye, Image, Settings } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function AdminPaymentsPanel({ authHeaders }) {
  const [configStatus, setConfigStatus] = useState(null);
  const [pending, setPending] = useState([]);
  const [showConfig, setShowConfig] = useState(false);
  const [configForm, setConfigForm] = useState({ key_id: "", key_secret: "", upi_id: "" });
  const [proofImage, setProofImage] = useState(null);
  const [proofPaymentId, setProofPaymentId] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/payments/config-status`, { headers: authHeaders });
      setConfigStatus(res.data);
    } catch {}
  }, [authHeaders]);

  const fetchPending = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/payments/pending`, { headers: authHeaders });
      setPending(res.data.payments || []);
    } catch {}
  }, [authHeaders]);

  useEffect(() => { fetchStatus(); fetchPending(); }, [fetchStatus, fetchPending]);

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
    } catch (err) { console.error(err); }
  };

  const viewProof = async (paymentId) => {
    try {
      const res = await axios.get(`${API}/admin/payments/${paymentId}/proof`, { headers: authHeaders });
      setProofImage(res.data.proof_image);
      setProofPaymentId(paymentId);
    } catch (err) { console.error(err); }
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
          <Button onClick={fetchPending} className="h-7 bg-emerald-600 text-white hover:bg-emerald-500 text-xs px-3" data-testid="payments-refresh">Refresh</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Config Status */}
        <div className="flex gap-3 text-[10px]" data-testid="payments-status">
          <span className={configStatus?.razorpay_configured ? "text-emerald-400" : "text-slate-500"}>
            Razorpay: {configStatus?.razorpay_configured ? "Configured" : "Not Set"}
          </span>
          <span className={configStatus?.upi_configured ? "text-emerald-400" : "text-slate-500"}>
            UPI QR: {configStatus?.upi_configured ? "Configured" : "Not Set"}
          </span>
        </div>

        {showConfig && (
          <form onSubmit={saveConfig} className="space-y-2 rounded-lg border border-slate-700 bg-slate-900/50 p-3" data-testid="payments-config-form">
            <p className="text-[10px] text-slate-400 font-semibold">Razorpay Credentials</p>
            <Input value={configForm.key_id} onChange={(e) => setConfigForm(p => ({ ...p, key_id: e.target.value }))} placeholder="Razorpay Key ID (rzp_...)" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="payments-key-id" />
            <Input type="password" value={configForm.key_secret} onChange={(e) => setConfigForm(p => ({ ...p, key_secret: e.target.value }))} placeholder="Razorpay Key Secret" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="payments-key-secret" />
            <p className="text-[10px] text-slate-400 font-semibold mt-2">UPI for QR Code (Offline Payments)</p>
            <Input value={configForm.upi_id} onChange={(e) => setConfigForm(p => ({ ...p, upi_id: e.target.value }))} placeholder="UPI ID (e.g. merchant@paytm)" className="border-slate-700 bg-slate-800 text-slate-100 text-xs h-8" data-testid="payments-upi-id" />
            <Button type="submit" className="h-7 bg-emerald-600 text-white hover:bg-emerald-500 text-xs" data-testid="payments-config-save">Save Configuration</Button>
          </form>
        )}

        {/* Pending Payments */}
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
