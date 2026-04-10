import { cn } from "@/lib/utils";

export function SubTabs({ tabs, active, onChange }) {
  return (
    <div className="mb-4 flex gap-1 rounded-lg border border-slate-800 bg-slate-950/80 p-1" data-testid="sub-tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          data-testid={`sub-tab-${tab.id}`}
          onClick={() => onChange(tab.id)}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
            active === tab.id
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent"
          )}
        >
          {tab.icon ? <tab.icon size={13} /> : null}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
