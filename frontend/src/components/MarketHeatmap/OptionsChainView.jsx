export function OptionsChainView({ chains, oiTypeFilter, minOI }) {
  if (!chains.length) return null;
  return (
    <div className="space-y-3" data-testid="options-chain-view">
      {chains.map(item => (
        <div key={item.symbol} className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono font-semibold text-sm text-slate-100">{item.symbol}</span>
            <div className="flex gap-3 text-xs text-slate-400">
              <span>Spot: <span className="text-cyan-300 font-mono">{item.spot?.toFixed(2)}</span></span>
              {item.expiry && <span>Exp: {item.expiry}</span>}
            </div>
          </div>
          {item.strikes?.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]" data-testid="options-chain-table">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-700">
                    <th className="px-2 py-1.5 text-right">CE OI</th>
                    <th className="px-2 py-1.5 text-right">CE IV</th>
                    <th className="px-2 py-1.5 text-right">CE LTP</th>
                    <th className="px-2 py-1.5 text-center font-bold text-cyan-400">Strike</th>
                    <th className="px-2 py-1.5 text-left">PE LTP</th>
                    <th className="px-2 py-1.5 text-left">PE IV</th>
                    <th className="px-2 py-1.5 text-left">PE OI</th>
                  </tr>
                </thead>
                <tbody>
                  {item.strikes
                    .filter(row => {
                      if (oiTypeFilter === "ce") return row.ce_ltp != null;
                      if (oiTypeFilter === "pe") return row.pe_ltp != null;
                      return true;
                    })
                    .filter(row => Math.max(row.ce_oi || 0, row.pe_oi || 0) >= minOI)
                    .map(row => {
                      const isATM = Math.abs(row.strike - item.spot) <= (item.step || 50);
                      return (
                        <tr key={row.strike} className={isATM ? "bg-cyan-900/20 font-bold" : "hover:bg-slate-800/40"}>
                          <td className="px-2 py-1 text-right font-mono text-emerald-400">{row.ce_oi ? (row.ce_oi / 1000).toFixed(0) + "K" : "--"}</td>
                          <td className="px-2 py-1 text-right font-mono text-violet-300">{row.ce_iv?.toFixed(1) || "--"}</td>
                          <td className="px-2 py-1 text-right font-mono text-slate-200">{row.ce_ltp?.toFixed(2) || "--"}</td>
                          <td className={`px-2 py-1 text-center font-mono ${isATM ? "text-cyan-300 text-xs" : "text-slate-400"}`}>{row.strike}</td>
                          <td className="px-2 py-1 text-left font-mono text-slate-200">{row.pe_ltp?.toFixed(2) || "--"}</td>
                          <td className="px-2 py-1 text-left font-mono text-violet-300">{row.pe_iv?.toFixed(1) || "--"}</td>
                          <td className="px-2 py-1 text-left font-mono text-rose-400">{row.pe_oi ? (row.pe_oi / 1000).toFixed(0) + "K" : "--"}</td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-slate-500 text-center py-2">No option chain data.</p>
          )}
        </div>
      ))}
    </div>
  );
}
