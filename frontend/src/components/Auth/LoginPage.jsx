import { useState, useRef } from "react";
import { KeyRound, Sparkles, AlertTriangle, Send, CreditCard, QrCode, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import axios from "axios";

const API = "/api";

export function LoginPage({ loginUsername, setLoginUsername, loginLoading, loginError, onLogin }) {
  const isSuspended = loginError && loginError.includes("ACCOUNT_SUSPENDED");
  const [reactivationMsg, setReactivationMsg] = useState("");
  const [reactivationSent, setReactivationSent] = useState(false);
  const [reactivationLoading, setReactivationLoading] = useState(false);
  const [paymentTab, setPaymentTab] = useState("razorpay"); // razorpay | qr | offline
  const [qrData, setQrData] = useState(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const fileInputRef = useRef(null);

  const handleReactivation = async (e) => {
    e.preventDefault();
    setReactivationLoading(true);
    try {
      await axios.post(`${API}/account/reactivation-request`, { message: reactivationMsg });
      setReactivationSent(true);
    } catch (err) {
      // If no incident found by IP, show generic message
      setReactivationSent(true);
    }
    setReactivationLoading(false);
  };

  // Parse the fraud details from error message
  const fraudDetails = isSuspended ? loginError.replace("ACCOUNT_SUSPENDED|", "") : "";

  return (
    <main className="min-h-screen dashboard-dark-bg text-slate-100" data-testid="login-page">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-4 py-10">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-cyan-500/40 bg-cyan-500/10 px-4 py-1 text-xs text-cyan-300" data-testid="login-chip">
          <Sparkles size={14} />
          TRADING RESEARCH PLATFORM
        </div>

        <h1 className="text-center text-4xl font-extrabold tracking-tight text-white sm:text-5xl lg:text-6xl" data-testid="login-title">
          Secure Access Dashboard
        </h1>

        <p className="mt-4 max-w-3xl text-center text-sm text-slate-300 sm:text-base" data-testid="login-subtitle">
          Login with your username credential. Public registration is disabled — users are created only by Admin/Owner.
        </p>

        <form onSubmit={onLogin} className="mt-8 w-full max-w-md space-y-3" data-testid="login-form">
          <Input
            value={loginUsername}
            onChange={(event) => setLoginUsername(event.target.value)}
            placeholder="Enter Username"
            className="h-11 border-slate-700 bg-slate-950 text-white placeholder:text-slate-400"
            data-testid="login-username-input"
          />
          <Button type="submit" className="h-11 w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="login-submit-button">
            <KeyRound size={16} />
            {loginLoading ? "Signing in..." : "Login"}
          </Button>
          {loginError && !isSuspended ? <p className="text-sm text-rose-400" data-testid="login-error">{loginError}</p> : null}
        </form>

        {/* ── Fraud Detection / Account Suspended Notice ── */}
        {isSuspended && (
          <Card className="mt-6 w-full max-w-lg border-rose-500/40 bg-rose-950/40" data-testid="fraud-detection-notice">
            <CardContent className="pt-5 space-y-3">
              <div className="flex items-center gap-2">
                <AlertTriangle size={20} className="text-rose-400" />
                <p className="text-base font-bold text-rose-300">Fraud Login Attempt Detected</p>
              </div>
              <p className="text-xs text-rose-200/80 leading-relaxed">{fraudDetails}</p>
              <div className="rounded-md border border-rose-700/40 bg-rose-950/60 p-3">
                <p className="text-xs text-rose-300 font-semibold">Reactivation Fee: INR 2,500</p>
                <p className="text-[10px] text-rose-400/70 mt-1">
                  Pay below to instantly reactivate, or upload proof for manual verification.
                </p>
              </div>

              {/* Payment Method Tabs */}
              <div className="flex gap-1 border-b border-rose-700/30 pb-1">
                {[
                  { id: "razorpay", label: "Pay Online", icon: CreditCard },
                  { id: "qr", label: "QR Code", icon: QrCode },
                  { id: "offline", label: "Upload Proof", icon: Upload },
                ].map(tab => (
                  <button key={tab.id} onClick={() => setPaymentTab(tab.id)} className={`flex items-center gap-1 px-3 py-1 rounded-t text-[10px] ${paymentTab === tab.id ? "bg-rose-700/30 text-rose-200" : "text-rose-400/60"}`} data-testid={`pay-tab-${tab.id}`}>
                    <tab.icon size={11} /> {tab.label}
                  </button>
                ))}
              </div>

              {/* Razorpay Online */}
              {paymentTab === "razorpay" && !reactivationSent && (
                <div className="space-y-2" data-testid="razorpay-section">
                  <Button onClick={async () => {
                    setReactivationLoading(true);
                    try {
                      const res = await axios.post(`${API}/payments/create-order`, { purpose: "reactivation" });
                      const { order_id, amount, key_id } = res.data;
                      if (!key_id) { setUploadStatus("Razorpay not configured. Use QR or upload proof."); setReactivationLoading(false); return; }
                      const options = {
                        key: key_id, amount, currency: "INR", order_id,
                        name: "Trading Platform", description: "Account Reactivation",
                        handler: async (response) => {
                          await axios.post(`${API}/payments/verify`, {
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_signature: response.razorpay_signature,
                            user_key: "",
                          });
                          setReactivationSent(true);
                        },
                        theme: { color: "#7c3aed" },
                      };
                      const rzp = new window.Razorpay(options);
                      rzp.open();
                    } catch (err) {
                      setUploadStatus(err?.response?.data?.detail || "Payment gateway unavailable. Use QR or upload.");
                    }
                    setReactivationLoading(false);
                  }} disabled={reactivationLoading} className="h-9 w-full bg-violet-600 text-white hover:bg-violet-500 text-xs" data-testid="razorpay-pay-btn">
                    <CreditCard size={14} className="mr-1.5" />
                    {reactivationLoading ? "Processing..." : "Pay INR 2,500 via Razorpay"}
                  </Button>
                  {uploadStatus && <p className="text-[10px] text-amber-300">{uploadStatus}</p>}
                </div>
              )}

              {/* QR Code */}
              {paymentTab === "qr" && !reactivationSent && (
                <div className="space-y-2 text-center" data-testid="qr-section">
                  {!qrData ? (
                    <Button onClick={async () => {
                      try {
                        const res = await axios.get(`${API}/payments/qr-code`);
                        setQrData(res.data);
                      } catch (err) { console.error("QR load failed:", err?.message); }
                    }} className="h-8 bg-slate-700 text-white hover:bg-slate-600 text-xs" data-testid="qr-load-btn">
                      <QrCode size={12} className="mr-1" /> Load QR Code
                    </Button>
                  ) : qrData.qr_available ? (
                    <div className="space-y-2">
                      <img src={qrData.qr_image} alt="UPI QR" className="mx-auto w-48 h-48 rounded-lg" data-testid="qr-image" />
                      <p className="text-[10px] text-rose-300">UPI: <span className="font-mono text-white">{qrData.upi_id}</span></p>
                      <p className="text-[10px] text-rose-300">Amount: <span className="font-mono text-white">INR {qrData.amount}</span></p>
                      <p className="text-[10px] text-rose-400/60">Scan with any UPI app, then upload screenshot as proof</p>
                    </div>
                  ) : (
                    <p className="text-[10px] text-amber-300">{qrData.message}</p>
                  )}
                </div>
              )}

              {/* Offline Upload */}
              {paymentTab === "offline" && !reactivationSent && (
                <div className="space-y-2" data-testid="offline-section">
                  <p className="text-[10px] text-rose-300">Upload a screenshot of your payment (UPI/NEFT/IMPS)</p>
                  <input ref={fileInputRef} type="file" accept="image/*" className="text-[10px] text-rose-200 file:bg-rose-700/30 file:text-rose-200 file:border-0 file:rounded file:px-3 file:py-1 file:text-[10px] file:mr-2" data-testid="offline-file-input" />
                  <textarea value={reactivationMsg} onChange={(e) => setReactivationMsg(e.target.value)} placeholder="Add notes (optional)" rows={2} className="w-full rounded border border-rose-700/40 bg-rose-950/60 text-rose-100 text-xs p-2 resize-none" data-testid="offline-notes" />
                  <Button onClick={async () => {
                    const file = fileInputRef.current?.files?.[0];
                    if (!file) { setUploadStatus("Please select a screenshot"); return; }
                    setReactivationLoading(true);
                    try {
                      const formData = new FormData();
                      formData.append("file", file);
                      formData.append("user_key", "");
                      formData.append("notes", reactivationMsg);
                      await axios.post(`${API}/payments/offline-upload?user_key=&notes=${encodeURIComponent(reactivationMsg)}`, formData, { headers: { "Content-Type": "multipart/form-data" } });
                      setReactivationSent(true);
                    } catch (err) { setUploadStatus(err?.response?.data?.detail || "Upload failed"); }
                    setReactivationLoading(false);
                  }} disabled={reactivationLoading} className="h-8 w-full bg-rose-600 text-white hover:bg-rose-500 text-xs" data-testid="offline-submit">
                    <Upload size={12} className="mr-1" />
                    {reactivationLoading ? "Uploading..." : "Upload Payment Proof"}
                  </Button>
                  {uploadStatus && <p className="text-[10px] text-amber-300">{uploadStatus}</p>}
                </div>
              )}

              {reactivationSent && (
                <div className="rounded-md border border-emerald-700/40 bg-emerald-950/30 p-3" data-testid="reactivation-success">
                  <p className="text-xs text-emerald-300 font-semibold">{paymentTab === "razorpay" ? "Payment Successful — Account Reactivated!" : "Proof Uploaded — Pending Admin Verification"}</p>
                  <p className="text-[10px] text-emerald-400/70 mt-0.5">{paymentTab === "razorpay" ? "You can now log in again." : "An administrator will verify your payment within 24 hours."}</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <Card className="mt-8 w-full max-w-4xl border-cyan-500/20 bg-slate-950/70" data-testid="login-disclaimer-card">
          <CardContent className="pt-5">
            <p className="text-sm font-semibold text-cyan-300">Personal Testing & Educational Disclaimer (SEBI-aligned)</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              This dashboard is for personal testing and educational analytics only. It does not provide investment advice,
              assured returns, or recommendation service. Please consult a SEBI-registered advisor before real trading.
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
