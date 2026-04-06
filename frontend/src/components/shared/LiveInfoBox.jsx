/**
 * Shared render helper components.
 * Extracted from App.js for modular reuse.
 */
import React from "react";
import { formatNumber, formatSignedPct, heatmapClass } from "../../utils/formatters";

export const LiveInfoBox = ({ signal, suffix }) => {
  const ltp = Number(signal.option_ltp);
  const dayLow = Number(signal.option_day_low);
  const dayHigh = Number(signal.option_day_high);
  const upFromLowPct = Number.isFinite(dayLow) && dayLow > 0 ? ((ltp - dayLow) / dayLow) * 100 : null;
  const downFromHighPct = Number.isFinite(dayHigh) && dayHigh > 0 ? ((ltp - dayHigh) / dayHigh) * 100 : null;

  return (
    <div className="fno-live-info-box" data-testid={`fno-live-info-box-${suffix}`}>
      <span className="fno-corner-delta-box" data-testid={`fno-corner-delta-box-${suffix}`}>
        <span className="fno-corner-row">
          <span className="fno-corner-label">Day Low:</span>
          <span className="fno-corner-value">{formatSignedPct(upFromLowPct)}</span>
        </span>
        <span className="fno-corner-row">
          <span className="fno-corner-label">Day High:</span>
          <span className="fno-corner-value">{formatSignedPct(downFromHighPct)}</span>
        </span>
      </span>
      <p className="text-[11px] font-extrabold">
        Live Option LTP: ₹{formatNumber(signal.option_ltp)}
      </p>
      <p className="text-[11px] font-extrabold">
        <span className="hidden sm:inline">Minimum Profit on Target1 on Current Buy:</span>
        <span className="sm:hidden">Min Profit @ T1 (Current Buy):</span>{" "}
        ₹{formatNumber(signal.ltp_margin_to_t1_amount)} ({formatNumber(signal.ltp_margin_to_t1_pct)}%)
      </p>
      <p className="text-[11px] font-extrabold">
        Day H/L: ₹{formatNumber(signal.option_day_high)} / ₹{formatNumber(signal.option_day_low)}
      </p>
      <p className={`mt-1 inline-flex rounded-md border px-2 py-0.5 text-[11px] font-extrabold ${heatmapClass(signal.achievable_profit_pct)}`}>
        Heatmap Ratio: {formatNumber(signal.achievable_profit_pct)}%
      </p>
    </div>
  );
};
