import { LogOut } from "lucide-react";
import { Button } from "components/ui/button";
import { SessionHealthIndicator } from "./SessionHealthIndicator";

export function AppHeader({ me, onLogout, authHeaders, notifBell }) {
  return (
    <header className="mb-6 rounded-2xl border border-slate-800 bg-slate-950/70 p-3 sm:p-4 shadow-lg" data-testid="app-header">
      <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3">
        <div className="min-w-0">
          <p className="text-[10px] sm:text-xs uppercase tracking-wide text-cyan-300">AI Trading Dashboard</p>
          <h1 className="text-lg sm:text-2xl md:text-3xl font-bold text-white truncate">Multibagger & F&O Projections</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <SessionHealthIndicator authHeaders={authHeaders} />
          {notifBell}
          <Button
            type="button"
            onClick={onLogout}
            className="border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800 text-xs sm:text-sm"
            data-testid="logout-button"
          >
            <LogOut size={14} />
            <span className="hidden sm:inline">Logout</span>
          </Button>
        </div>
      </div>

      <div className="mt-3 sm:mt-4 grid grid-cols-2 gap-2 sm:gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-2 sm:p-3" data-testid="summary-username">
          <p className="text-[10px] sm:text-xs text-slate-400">Username</p>
          <p className="font-mono text-xs sm:text-sm text-cyan-300 truncate">{me.username}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-2 sm:p-3" data-testid="summary-role">
          <p className="text-[10px] sm:text-xs text-slate-400">Role</p>
          <p className="font-mono text-xs sm:text-sm text-cyan-300">{me.role}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-2 sm:p-3" data-testid="summary-credits">
          <p className="text-[10px] sm:text-xs text-slate-400">Credits</p>
          <p className="font-mono text-xs sm:text-sm text-cyan-300">{me.admin_exempt ? "EXEMPT" : me.credits}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-2 sm:p-3" data-testid="summary-cost-note">
          <p className="text-[10px] sm:text-xs text-slate-400">Cost</p>
          <p className="font-mono text-[10px] sm:text-sm text-cyan-300 leading-tight">MB:2 | F&O:2 | Custom:1 | Port:0.2/stk</p>
        </div>
      </div>
    </header>
  );
}
