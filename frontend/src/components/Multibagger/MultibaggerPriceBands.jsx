import { formatNumber } from "@/utils/formatters";

export function MultibaggerPriceBands({ row, expanded, onToggle }) {
  return (
    <>
      <button
        className="text-xs text-cyan-400 hover:text-cyan-300 underline"
        onClick={onToggle}
        data-testid={`multibagger-bands-toggle-${row.symbol.toLowerCase()}`}
      >
        {expanded ? "Hide" : "Show"} Price Bands (Conservative / Expected / Optimistic)
      </button>
      {expanded ? (
        <div className="mt-2 overflow-auto" data-testid={`multibagger-bands-table-${row.symbol.toLowerCase()}`}>
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-1 pr-3">Horizon</th>
                <th className="text-right py-1 pr-3">Conservative</th>
                <th className="text-right py-1 pr-3">Expected Upside</th>
                <th className="text-right py-1 pr-3">Expected Downside</th>
                <th className="text-right py-1 pr-3">Optimistic</th>
                <th className="text-right py-1 pr-3">HV%</th>
                <th className="text-right py-1">Signal</th>
              </tr>
            </thead>
            <tbody>
              {["1W","1M","3M","6M","9M","1Y"].map(h => {
                const b = row.vol_bands[h];
                if (!b) return null;
                const ltp = row.ltp || 0;
                return (
                  <tr key={h} className="border-b border-slate-800/40">
                    <td className="py-1 pr-3 font-mono font-semibold text-slate-300">{h}</td>
                    <td className="text-right pr-3 text-yellow-300">+{b.conservative_high_pct?.toFixed(1)}%</td>
                    <td className="text-right pr-3 text-emerald-300">+{b.upside_pct?.toFixed(1)}% (₹{formatNumber(ltp * (1 + b.upside_pct/100))})</td>
                    <td className="text-right pr-3 text-rose-300">{b.downside_pct?.toFixed(1)}% (₹{formatNumber(ltp * (1 + b.downside_pct/100))})</td>
                    <td className="text-right pr-3 text-cyan-300">+{b.optimistic_high_pct?.toFixed(1)}%</td>
                    <td className="text-right pr-3 text-slate-400">{b.hist_vol_pct?.toFixed(1)}%</td>
                    <td className="text-right">
                      <span className={`rounded px-1 ${b.flag === 'GREEN' ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>{b.flag}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-1 text-slate-500">Based on {row.vol_bands["1M"]?.hist_vol_pct?.toFixed(1)}% annualized historical volatility. Conservative = 1σ, Expected = 1.5σ, Optimistic = 2σ.</p>
        </div>
      ) : null}
    </>
  );
}
