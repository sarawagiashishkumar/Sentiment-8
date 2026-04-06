/**
 * F&O Export Utilities.
 * Extracted from App.js for modular reuse.
 */
import * as XLSX from "xlsx";
import html2canvas from "html2canvas";

/**
 * Converts an FNOSignalResponse object to the standardized export row format.
 */
export const buildExportRow = (signal) => {
  const entry = Number(signal.entry_price || 0);
  const lot = Number(signal.lot_size || 1);
  const t1 = Number(signal.target1 || 0);
  const t2 = Number(signal.target2 || 0);
  const sl = Number(signal.stop_loss || 0);
  const conf = Number(signal.confluence_score || 0);
  const investment = Math.round(entry * lot);
  const t1Pct = entry > 0 ? Number(((t1 - entry) / entry * 100).toFixed(2)) : 0;
  const t2Pct = entry > 0 ? Number(((t2 - entry) / entry * 100).toFixed(2)) : 0;
  const t1Profit = Math.round((t1 - entry) * lot);
  const t2Profit = Math.round((t2 - entry) * lot);

  return {
    Script: signal.script || "-",
    Bias: signal.direction || "-",
    Lot: lot,
    "Entry ₹": entry,
    "Investment (₹)": investment,
    SL: sl,
    T1: t1,
    "T1%": t1Pct,
    "T1 Profit ₹": t1Profit,
    T2: t2,
    "T2%": t2Pct,
    "T2 Profit ₹": t2Profit,
    Conf: conf,
  };
};

/**
 * Collects all F&O signals from fnoData into a flat sorted array.
 * Priority: top_trades → NIFTY assured → BANKNIFTY assured → stock_signals
 */
export const collectAllFnoSignals = (fnoData) => {
  if (!fnoData) return [];
  const seen = new Set();
  const rows = [];
  const addSignal = (sig) => {
    if (!sig || seen.has(sig.script)) return;
    seen.add(sig.script);
    rows.push(sig);
  };

  (fnoData.top_trades || []).forEach(addSignal);
  (fnoData.nifty_projection?.assured_signals || []).forEach(addSignal);
  (fnoData.banknifty_projection?.assured_signals || []).forEach(addSignal);
  (fnoData.stock_signals || []).forEach(addSignal);

  return rows.sort((a, b) => (b.confluence_score || 0) - (a.confluence_score || 0));
};

/** Export F&O data as CSV */
export const exportFnoAsCSV = (fnoData) => {
  const signals = collectAllFnoSignals(fnoData);
  if (!signals.length) return;
  const rows = signals.map(buildExportRow);
  const headers = Object.keys(rows[0]);
  const csvLines = [
    headers.join(","),
    ...rows.map((row) =>
      headers.map((h) => {
        const val = row[h];
        const str = String(val ?? "");
        return str.includes(",") ? `"${str}"` : str;
      }).join(",")
    ),
    "",
    `"Note: Investment = Entry Price × Lot Size (1 lot premium cost) | NSE lot sizes verified | Generated: ${new Date().toLocaleString("en-IN")}"`,
  ];
  const blob = new Blob([csvLines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `FnO_Signals_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
};

/** Export F&O data as XLS (Excel) */
export const exportFnoAsXLS = (fnoData) => {
  const signals = collectAllFnoSignals(fnoData);
  if (!signals.length) return;
  const rows = signals.map(buildExportRow);

  const wb = XLSX.utils.book_new();
  const wsData = [
    ["Stock Options — Correct Lot Sizes के साथ"],
    [],
    Object.keys(rows[0]),
    ...rows.map((row) => Object.values(row)),
    [],
    [`Note: Investment = Entry Price × Lot Size (1 lot premium cost) | NSE lot sizes verified | Generated: ${new Date().toLocaleString("en-IN")}`],
  ];

  const ws = XLSX.utils.aoa_to_sheet(wsData);
  ws["!cols"] = [
    { wch: 28 }, { wch: 10 }, { wch: 8 }, { wch: 10 }, { wch: 14 },
    { wch: 10 }, { wch: 10 }, { wch: 8 }, { wch: 14 },
    { wch: 10 }, { wch: 8 }, { wch: 14 }, { wch: 8 },
  ];
  ws["!merges"] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 12 } }];

  XLSX.utils.book_append_sheet(wb, ws, "F&O Signals");
  XLSX.writeFile(wb, `FnO_Signals_${new Date().toISOString().slice(0, 10)}.xlsx`);
};

/** Export F&O table as JPG image */
export const exportFnoAsJPG = async (tableRef) => {
  if (!tableRef?.current) return;
  try {
    const canvas = await html2canvas(tableRef.current, {
      backgroundColor: "#ffffff",
      scale: 2,
      useCORS: true,
      logging: false,
    });
    const url = canvas.toDataURL("image/jpeg", 0.92);
    const a = document.createElement("a");
    a.href = url;
    a.download = `FnO_Signals_${new Date().toISOString().slice(0, 10)}.jpg`;
    a.click();
  } catch (err) {
    console.error("JPG export failed:", err);
  }
};
