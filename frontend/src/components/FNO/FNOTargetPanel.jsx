import { formatNumber } from "@/utils/formatters";

export function FNOTargetPanel({ signal }) {
  if (!signal.best_exit_price) return null;
  return (
    <p className="text-green-400 font-semibold text-sm">
      * BEST EXIT: T+{signal.best_exit_days} Trading Days{signal.best_exit_date_str ? ` (${signal.best_exit_date_str})` : ""} @ ₹{formatNumber(signal.best_exit_price)}
    </p>
  );
}
