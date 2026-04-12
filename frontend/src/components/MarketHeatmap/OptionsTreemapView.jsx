export function OptionsTreemapView({ contracts }) {
  if (!contracts.length) return null;
  return (
    <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-9 gap-px bg-slate-800 rounded-lg overflow-hidden" data-testid="options-treemap-view">
      {contracts.slice(0, 500).map((c, idx) => {
        const bgCls = c.type === "CE"
          ? "bg-gradient-to-br from-emerald-800/80 to-teal-900/70"
          : "bg-gradient-to-br from-purple-800/80 to-pink-900/70";
        return (
          <div key={`${c.ts}-${idx}`}
            data-testid={`option-tile-${idx}`}
            className={`${bgCls} p-2 flex flex-col items-center justify-center text-white transition-all hover:brightness-125`}
            title={`OI: ${c.oi ? (c.oi/1000).toFixed(0) + 'K' : '0'} | IV: ${c.iv?.toFixed(1) || '--'}`}
          >
            <span className="font-mono text-[7px] text-slate-300 truncate w-full text-center">{c.ts}</span>
            <span className="font-mono text-sm font-bold mt-0.5">Rs.{c.ltp?.toFixed(2) || "0"}</span>
            <span className="font-mono text-[8px] text-slate-400 mt-0.5">OI: {c.oi ? (c.oi/1000).toFixed(0) + 'K' : '0'}</span>
          </div>
        );
      })}
    </div>
  );
}
