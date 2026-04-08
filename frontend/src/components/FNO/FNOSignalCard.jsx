import { formatNumber, formatExpiryDate, directionBadge, qualityBadge } from "@/utils/formatters";
import { Badge } from "@/components/ui/badge";
import { LiveInfoBox } from "@/components/shared/LiveInfoBox";
import { FNOIVBadge } from "./FNOIVBadge";

const variantStyles = {
  assured: "rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs",
  watchlist: "rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs",
  stock: "rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs",
  top4: "rounded-md border border-slate-800 bg-slate-900/70 p-3 text-xs",
};

export function FNOSignalCard({ signal, suffix, variant = "assured" }) {
  const style = variantStyles[variant] || variantStyles.assured;
  const isTop4 = variant === "top4";
  const isStock = variant === "stock";
  const isWatchlist = variant === "watchlist";
  const isAssured = variant === "assured";

  const testIdAttr = isStock
    ? { "data-testid": `stock-fno-signal-${signal.script.toLowerCase()}` }
    : isTop4
    ? { "data-testid": `top4-trade-${signal.script.toLowerCase()}` }
    : {};

  return (
    <div className={`result-hover ${style}`} {...testIdAttr}>
      {/* Header: Script + Badge */}
      <div className={`${isStock || isTop4 ? "mb-2" : "mb-1"} flex items-center justify-between ${isStock ? "gap-2" : ""}`}>
        {isStock ? (
          <p className="font-mono text-cyan-200">{signal.script}</p>
        ) : (
          <span className={`font-mono ${isWatchlist ? "text-emerald-200" : "text-cyan-200"}`}>{signal.script}</span>
        )}
        {isTop4 ? (
          <Badge className={`border ${qualityBadge(signal.signal_quality)}`}>{signal.signal_quality}</Badge>
        ) : (
          <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
        )}
      </div>

      {/* LiveInfoBox */}
      <LiveInfoBox signal={signal} suffix={suffix} />

      {/* Expiry */}
      {!isTop4 && (
        <p data-testid={isStock ? `stock-fno-signal-expiry-${signal.script.toLowerCase()}` : undefined}>
          Expiry: {formatExpiryDate(signal.expiry)}
          {signal.remaining_trading_days > 0 ? ` \u00b7 ${signal.remaining_trading_days} trading days left` : ""}
          {isStock ? " (monthly stock contract)" : ""}
        </p>
      )}

      {/* Expiry badges */}
      {signal.expiry_today_badge ? (
        <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse">
          EXPIRY TODAY — Exit Before 3:30 PM
        </span>
      ) : signal.near_expiry_badge ? (
        <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
          {isTop4 ? `\u26a0 Near Expiry (${signal.remaining_trading_days} days)` : "\u26a0 Near Expiry"}
        </span>
      ) : null}

      {/* Entry/SL/T1/T2 */}
      {(isAssured || isWatchlist) ? (
        <p>Entry/SL/T1/T2: ₹{formatNumber(signal.entry_price)} / ₹{formatNumber(signal.stop_loss)} / ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
      ) : (
        <>
          <p>Entry: ₹{formatNumber(signal.entry_price)}</p>
          <p>SL: ₹{formatNumber(signal.stop_loss)}</p>
          <p>T1/T2: ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
        </>
      )}

      {/* Confluence/Confidence */}
      {isTop4 ? (
        <p>Confidence: {signal.confluence_score >= 80 ? "\u2b50 " : ""}{signal.confluence_score} | {signal.direction}</p>
      ) : isStock ? (
        <p>Confidence: {signal.confluence_score >= 80 ? "\u2b50 " : ""}{signal.confluence_score}</p>
      ) : (
        <p>Confluence: {signal.confluence_score >= 80 ? "\u2b50 " : ""}{signal.confluence_score} ({signal.signal_quality})</p>
      )}

      {/* Best Exit */}
      {signal.best_exit_price && (
        <p className="text-green-400 font-semibold text-sm">
          \u2b50 BEST EXIT: T+{signal.best_exit_days} Trading Days{signal.best_exit_date_str ? ` (${signal.best_exit_date_str})` : ""} @ ₹{formatNumber(signal.best_exit_price)}
        </p>
      )}

      {/* Not Affordable Alert (P2-B) */}
      {signal.not_affordable && (
        <div className="mt-1 p-1.5 rounded border border-rose-600/50 bg-rose-950/30" data-testid={`not-affordable-alert-${signal.script?.toLowerCase()}-${variant}`}>
          <span className="font-bold text-rose-300 text-xs">Exceeds Budget</span>
          <span className="text-rose-200 text-xs ml-1">
            {signal.sizing_info?.sizing_reason || "Capital for 1 lot exceeds your F\u0026O budget"}
          </span>
        </div>
      )}

      {/* Budget Entry Alert */}
      {signal.budget_entry_alert && signal.best_budget_entry && (
        <div className="mt-1 p-1.5 rounded border border-amber-600/50 bg-amber-950/30" data-testid={`budget-entry-alert-${signal.script?.toLowerCase()}-${variant}`}>
          <span className="font-bold text-amber-300 text-xs">{"\u23f3"} Wait for Budget Entry</span>
          <span className="text-amber-100 text-xs ml-1">Pullback to ₹{formatNumber(signal.best_budget_entry)} — do not enter at ₹{formatNumber(signal.entry_price)}</span>
        </div>
      )}

      {/* Position Sizing Info (P2-C compact display) */}
      {signal.sizing_info && !signal.not_affordable && signal.sizing_info.lots_allowed > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5 text-xs" data-testid={`sizing-info-${signal.script?.toLowerCase()}-${variant}`}>
          <span className="rounded px-1.5 py-0.5 bg-slate-800/70 text-slate-300">
            Lots: {signal.sizing_info.lots_allowed}
          </span>
          {signal.sizing_info.lots_atr_method > 0 && (
            <span className="rounded px-1.5 py-0.5 bg-indigo-900/50 text-indigo-300">
              ATR: {signal.sizing_info.lots_atr_method}
            </span>
          )}
          {signal.sizing_info.lots_fixed_risk > 0 && (
            <span className="rounded px-1.5 py-0.5 bg-violet-900/50 text-violet-300">
              Risk: {signal.sizing_info.lots_fixed_risk}
            </span>
          )}
          {signal.sizing_info.max_risk_Rs > 0 && (
            <span className="rounded px-1.5 py-0.5 bg-slate-800/70 text-slate-400">
              Max₹{Number(signal.sizing_info.max_risk_Rs).toLocaleString("en-IN")}
            </span>
          )}
        </div>
      )}

      {/* Day Change + Bias (shown for assured, stock, top4 — not watchlist) */}
      {!isWatchlist && (signal.underlying_day_change_pct !== null || signal.underlying_bias_score !== null) && (
        <div className="mt-1 flex flex-wrap gap-2">
          {signal.underlying_day_change_pct !== null && (
            <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.underlying_day_change_pct >= 0 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>
              Day Change: {signal.underlying_day_change_pct?.toFixed(2)}%
            </span>
          )}
          {signal.underlying_bias_score !== null && (
            <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.underlying_bias_score >= 0 ? 'bg-blue-900/50 text-blue-300' : 'bg-orange-900/50 text-orange-300'}`}>
              Bias: {signal.underlying_bias_score?.toFixed(2)}
            </span>
          )}
        </div>
      )}

      {/* IV Badges (assured + top4 only) */}
      {(isAssured || isTop4) && <FNOIVBadge signal={signal} testIdPrefix={isTop4 ? "top4" : ""} />}

      {/* Caution warning (assured only) */}
      {isAssured && String(signal.strategy || "").toUpperCase().includes("CAUTION") ? (
        <p className="font-semibold text-amber-200">{"\u26a0"} Caution: Probable setup only. Use strict stop-loss and position sizing.</p>
      ) : null}

      {/* Trigger factors (top4 only) */}
      {isTop4 && (
        <p className="text-slate-400">{(signal.trigger_factors || []).slice(0, 2).join(" | ")}</p>
      )}
    </div>
  );
}
