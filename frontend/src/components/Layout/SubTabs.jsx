export function SubTabs({ tabs, active, onChange }) {
  return (
    <div className="mb-4 -mx-1 px-1 overflow-x-auto scrollbar-hide" data-testid="sub-tabs">
      <div className="flex items-center gap-1 min-w-max pb-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            data-testid={`sub-tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs sm:text-sm font-medium transition-all shrink-0 ${
              active === tab.id
                ? "bg-cyan-600 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
