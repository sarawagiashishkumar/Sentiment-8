export function SubTabs({ tabs, active, onChange }) {
  return (
    <div className="flex items-center gap-1 mb-4" data-testid="sub-tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          data-testid={`sub-tab-${tab.id}`}
          onClick={() => onChange(tab.id)}
          className={`rounded-md px-3.5 py-1.5 text-sm font-medium transition-all ${
            active === tab.id
              ? "bg-cyan-600 text-white"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
