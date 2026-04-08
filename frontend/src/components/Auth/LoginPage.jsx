import { KeyRound, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function LoginPage({ loginUsername, setLoginUsername, loginLoading, loginError, onLogin }) {
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
          {loginError ? <p className="text-sm text-rose-400" data-testid="login-error">{loginError}</p> : null}
        </form>

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
