import { Badge } from "@/components/ui/badge";
import { TableBody, TableCell, TableRow } from "@/components/ui/table";
import { formatNumber, scoreBadge } from "@/utils/formatters";
import { MultibaggerPriceBands } from "./MultibaggerPriceBands";

export function MultibaggerCandidateCard({ row, expanded, onToggleBands }) {
  return (
    <TableBody key={`group-${row.symbol}`} className="multibagger-group cursor-pointer">
      <TableRow data-testid={`multibagger-target-row-${row.symbol.toLowerCase()}`}>
        <TableCell className="font-mono text-cyan-300">{row.company_name}</TableCell>
        <TableCell>{row.sector}</TableCell>
        <TableCell className="font-mono">{formatNumber(row.current_rsi_level)}</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.gtt_buy_price)}</TableCell>
        <TableCell className="text-slate-400">Targeted Upside Price</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["1W"])}</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["1M"])}</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["3M"])}</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["6M"])}</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["9M"])}</TableCell>
        <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["1Y"])}</TableCell>
        <TableCell>
          <Badge className={`border ${scoreBadge(row.is_potential_multibagger)}`}>{row.multibagger_score}</Badge>
        </TableCell>
      </TableRow>
      <TableRow data-testid={`multibagger-roi-row-${row.symbol.toLowerCase()}`}>
        <TableCell className="font-mono text-slate-400">{row.symbol}</TableCell>
        <TableCell className="text-slate-500">Tier: {row.tier_pass_count}/8</TableCell>
        <TableCell className="text-slate-500">LTP: ₹{formatNumber(row.ltp)}</TableCell>
        <TableCell className="text-slate-500">PE: {formatNumber(row.pe_ratio)}</TableCell>
        <TableCell className="text-slate-400">% Profit</TableCell>
        <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["1W"])}%</TableCell>
        <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["1M"])}%</TableCell>
        <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["3M"])}%</TableCell>
        <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["6M"])}%</TableCell>
        <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["9M"])}%</TableCell>
        <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["1Y"])}%</TableCell>
        <TableCell>
          <Badge className={`border ${scoreBadge(row.is_potential_multibagger)}`}>{row.is_potential_multibagger ? "POTENTIAL" : "WATCH"}</Badge>
        </TableCell>
      </TableRow>
      {(row.roe != null || row.roce != null || row.piotroski_score != null || row.beneish_m_score != null || row.eps_growth_pct != null) ? (
        <TableRow data-testid={`multibagger-fundamentals-row-${row.symbol.toLowerCase()}`}>
          <TableCell colSpan={12} className="py-1 bg-slate-900/40">
            <div className="flex flex-wrap gap-2 text-xs">
              {row.roe != null && (
                <span className={`rounded px-2 py-0.5 font-semibold ${row.roe >= 20 ? 'bg-emerald-900/50 text-emerald-300' : row.roe >= 12 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>ROE: {row.roe}%</span>
              )}
              {row.roce != null && (
                <span className={`rounded px-2 py-0.5 font-semibold ${row.roce >= 15 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-yellow-900/50 text-yellow-300'}`}>ROCE: {row.roce}%</span>
              )}
              {row.piotroski_score != null && (
                <span className={`rounded px-2 py-0.5 font-semibold ${row.piotroski_score >= 7 ? 'bg-emerald-900/50 text-emerald-300' : row.piotroski_score >= 5 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>Piotroski: {row.piotroski_score}/9</span>
              )}
              {row.beneish_m_score != null && (
                <span className={`rounded px-2 py-0.5 font-semibold ${row.beneish_m_score <= -2.22 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>Beneish M: {row.beneish_m_score} {row.beneish_m_score > -2.22 ? '\u26a0' : '\u2713'}</span>
              )}
              {row.eps_growth_pct != null && (
                <span className={`rounded px-2 py-0.5 font-semibold ${row.eps_growth_pct > 0 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>EPS Growth: {row.eps_growth_pct > 0 ? '+' : ''}{row.eps_growth_pct}%</span>
              )}
              {row.debt_to_equity != null && (
                <span className={`rounded px-2 py-0.5 font-semibold ${row.debt_to_equity < 0.5 ? 'bg-emerald-900/50 text-emerald-300' : row.debt_to_equity < 1.5 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>D/E: {Number(row.debt_to_equity).toFixed(2)}</span>
              )}
            </div>
          </TableCell>
        </TableRow>
      ) : null}
      <TableRow data-testid={`multibagger-thesis-row-${row.symbol.toLowerCase()}`}>
        <TableCell colSpan={12} className="py-2 text-xs text-slate-300 leading-relaxed border-b border-slate-800/60">
          <span className="font-semibold text-cyan-400 mr-2">Thesis:</span>
          {(row.thesis || "No thesis available").split(" | ").map((part, i) => (
            <span key={i} className="inline-block mr-3 mb-1">
              {i > 0 && <span className="text-slate-600 mr-3">|</span>}
              {part}
            </span>
          ))}
        </TableCell>
      </TableRow>
      {row.vol_bands ? (
        <TableRow data-testid={`multibagger-bands-toggle-row-${row.symbol.toLowerCase()}`}>
          <TableCell colSpan={12} className="py-1 bg-slate-900/20">
            <MultibaggerPriceBands row={row} expanded={expanded} onToggle={onToggleBands} />
          </TableCell>
        </TableRow>
      ) : null}
    </TableBody>
  );
}
