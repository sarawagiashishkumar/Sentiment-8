import { useState } from "react";
import { KeyRound, Sparkles, AlertTriangle, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function LoginPage({ loginUsername, setLoginUsername, loginLoading, loginError, onLogin }) {
  const isSuspended = loginError && loginError.includes("ACCOUNT_SUSPENDED");
  const [reactivationMsg, setReactivationMsg] = useState("");
  const [reactivationSent, setReactivationSent] = useState(false);
  const [reactivationLoading, setReactivationLoading] = useState(false);

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
                  To reactivate your account, submit the form below. An administrator will review your request.
                </p>
              </div>
              {!reactivationSent ? (
                <form onSubmit={handleReactivation} className="space-y-2" data-testid="reactivation-form">
                  <textarea
                    value={reactivationMsg}
                    onChange={(e) => setReactivationMsg(e.target.value)}
                    placeholder="Explain the situation (e.g., I was traveling, VPN change, etc.)"
                    rows={3}
                    className="w-full rounded border border-rose-700/40 bg-rose-950/60 text-rose-100 text-xs p-2 resize-none placeholder:text-rose-400/50"
                    data-testid="reactivation-message"
                  />
                  <Button type="submit" disabled={reactivationLoading} className="h-8 bg-rose-600 text-white hover:bg-rose-500 text-xs" data-testid="reactivation-submit">
                    <Send size={12} className="mr-1" />
                    {reactivationLoading ? "Submitting..." : "Submit Reactivation Request"}
                  </Button>
                </form>
              ) : (
                <div className="rounded-md border border-emerald-700/40 bg-emerald-950/30 p-3" data-testid="reactivation-success">
                  <p className="text-xs text-emerald-300 font-semibold">Request Submitted</p>
                  <p className="text-[10px] text-emerald-400/70 mt-0.5">An administrator will review your case and contact you.</p>
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
