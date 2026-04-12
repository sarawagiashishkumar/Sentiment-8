/**
 * Application-wide formatting and display utilities.
 * Extracted from App.js for modular reuse.
 */

export const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
};

export const formatTime = (iso) => {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

export const formatExpiryDate = (isoDate) => {
  if (!isoDate) return "-";
  const match = String(isoDate).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  return `${day}-${month}-${year}`;
};

export const formatSignedInr = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : numeric < 0 ? "-" : "";
  return `${sign}₹${Math.abs(numeric).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
};

export const heatmapClass = (pct) => {
  const value = Number(pct || 0);
  if (value >= 10) return "bg-emerald-500/30 border-emerald-400 text-emerald-100";
  if (value >= 6) return "bg-amber-500/30 border-amber-300 text-amber-100";
  return "bg-rose-500/30 border-rose-300 text-rose-100";
};

export const formatSignedPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(2)}%`;
};

export const directionBadge = (direction) => {
  if (direction === "BULLISH") return "bg-emerald-600 text-white border-emerald-700";
  if (direction === "BEARISH") return "bg-rose-600 text-white border-rose-700";
  return "bg-slate-300 text-slate-800 border-slate-400";
};

export const qualityBadge = (quality) => {
  if (quality === "HIGH") return "bg-emerald-600 text-white border-emerald-700";
  if (quality === "MEDIUM") return "bg-amber-500 text-white border-amber-600";
  return "bg-slate-300 text-slate-800 border-slate-400";
};

export const scoreBadge = (isPotential) =>
  isPotential
    ? "bg-cyan-500 text-slate-900 border-cyan-600"
    : "bg-slate-700 text-slate-200 border-slate-500";
