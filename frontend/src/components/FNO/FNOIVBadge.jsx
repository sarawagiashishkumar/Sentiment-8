export function FNOIVBadge({ signal, testIdPrefix = "" }) {
  if (signal.iv_rank_52w === null && signal.atm_iv === null) return null;
  const pfx = testIdPrefix ? `${testIdPrefix}-` : "";
  return (
    <div className="mt-1 flex flex-wrap gap-2">
      {signal.atm_iv !== null && (
        <span className="rounded px-1.5 py-0.5 text-xs font-semibold bg-violet-900/50 text-violet-300" data-testid={`atm-iv-${pfx}${signal.script?.toLowerCase()}`}>
          ATM IV: {signal.atm_iv?.toFixed(1)}%
        </span>
      )}
      {signal.iv_rank_52w !== null && (
        <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.iv_rank_52w >= 70 ? 'bg-red-900/50 text-red-300' : signal.iv_rank_52w <= 30 ? 'bg-green-900/50 text-green-300' : 'bg-zinc-800/50 text-zinc-300'}`} data-testid={`iv-rank-52w-${pfx}${signal.script?.toLowerCase()}`}>
          IV Rank 52W: {signal.iv_rank_52w?.toFixed(1)}%
        </span>
      )}
    </div>
  );
}
