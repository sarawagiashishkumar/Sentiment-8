import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SessionHealthIndicator } from "./SessionHealthIndicator";

export function AppHeader({ me, onLogout, authHeaders }) {
  return (
    <header className="mb-6 rounded-2xl border border-slate-800 bg-slate-950/70 p-4 shadow-lg" data-testid="app-header">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-cyan-300">AI Trading Dashboard</p>
          <h1 className="text-2xl font-bold text-white sm:text-3xl">Multibagger & F&O Projections</h1>
        </div>
        <div className="flex items-center gap-2">
          <SessionHealthIndicator authHeaders={authHeaders} />
          <Button
            type="button"
            onClick={onLogout}
            className="border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"
            data-testid="logout-button"
          >
            <LogOut size={16} />
            Logout
          </Button>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-username">
          <p className="text-xs text-slate-400">Username</p>
          <p className="font-mono text-sm text-cyan-300">{me.username}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-role">
          <p className="text-xs text-slate-400">Role</p>
          <p className="font-mono text-sm text-cyan-300">{me.role}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-credits">
          <p className="text-xs text-slate-400">Credits</p>
          <p className="font-mono text-sm text-cyan-300">{me.admin_exempt ? "EXEMPT" : me.credits}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-cost-note">
          <p className="text-xs text-slate-400">Generation Cost</p>
          <p className="font-mono text-sm text-cyan-300">Multibagger:2 | F&O:2 | Custom F&O:1 | Portfolio:0.2/stock</p>
        </div>
      </div>
    </header>
  );
}
