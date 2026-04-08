/**
 * F&O Export Utilities — Re-ordered columns + PDF + Word support.
 * Column order (Master Spec):
 *  1. Script   2. Bias      3. Lot       4. Entry ₹   5. SL
 *  6. T1       7. T2        8. Investment 9. T1%      10. T1 Profit ₹
 * 11. T2%     12. T2 Profit 13. Conf     14. Best Exit ₹  [⭐ if Best Exit ≥ T2 × 1.2]
 */
import * as XLSX from "xlsx";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import { Document, Packer, Paragraph, Table, TableRow, TableCell, TextRun, WidthType, AlignmentType, HeadingLevel } from "docx";

const DATE_LABEL = new Date().toLocaleString("en-IN");
const FILE_DATE = new Date().toISOString().slice(0, 10);
const NOTE = `Investment = Entry Price × Lot Size (1 lot premium cost) | NSE lot sizes verified | Generated: ${DATE_LABEL}`;

/**
 * Converts an FNOSignalResponse to the standardized 14-column export row.
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

  // Best Exit: replaces "Bias Point". Apply ⭐ Golden Star when Best Exit ≥ T2 × 1.2
  const bestExitRaw = Number(signal.best_exit_price || 0);
  const bestExitLabel = bestExitRaw > 0 && t2 > 0 && bestExitRaw >= t2 * 1.2
    ? `\u2B50 ${bestExitRaw.toFixed(2)}`   // ⭐ prefix = premium > 20% above T2
    : bestExitRaw > 0 ? bestExitRaw.toFixed(2) : "-";

  // Ordered per Master Spec Col 1-14
  return {
    Script: signal.script || "-",
    Bias: signal.direction || "-",
    Lot: lot,
    "Entry \u20B9": entry,
    SL: sl,
    T1: t1,
    T2: t2,
    "Investment (\u20B9)": investment,
    "T1%": t1Pct,
    "T1 Profit \u20B9": t1Profit,
    "T2%": t2Pct,
    "T2 Profit \u20B9": t2Profit,
    Conf: conf,
    "ATM IV": signal.atm_iv != null ? signal.atm_iv.toFixed(1) + "%" : "-",
    "IV Rank 52W": signal.iv_rank_52w != null ? signal.iv_rank_52w.toFixed(1) + "%" : "-",
    "Best Exit \u20B9": bestExitLabel,
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
    `"${NOTE}"`,
  ];
  const blob = new Blob([csvLines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `FnO_Signals_${FILE_DATE}.csv`;
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
    ["Stock F&O Signals — NSE Verified Lot Sizes"],
    [],
    Object.keys(rows[0]),
    ...rows.map((row) => Object.values(row)),
    [],
    [NOTE],
  ];

  const ws = XLSX.utils.aoa_to_sheet(wsData);
  // Col widths for 14 columns
  ws["!cols"] = [
    { wch: 28 }, { wch: 10 }, { wch: 7 }, { wch: 10 }, { wch: 10 },
    { wch: 10 }, { wch: 10 }, { wch: 14 }, { wch: 8 }, { wch: 14 },
    { wch: 8 }, { wch: 14 }, { wch: 7 }, { wch: 11 },
  ];
  ws["!merges"] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 13 } }];

  XLSX.utils.book_append_sheet(wb, ws, "F&O Signals");
  XLSX.writeFile(wb, `FnO_Signals_${FILE_DATE}.xlsx`);
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
    a.download = `FnO_Signals_${FILE_DATE}.jpg`;
    a.click();
  } catch (err) {
    console.error("JPG export failed:", err);
  }
};

/** Export F&O data as PDF */
export const exportFnoAsPDF = (fnoData) => {
  const signals = collectAllFnoSignals(fnoData);
  if (!signals.length) return;
  const rows = signals.map(buildExportRow);
  const headers = Object.keys(rows[0]);
  const body = rows.map((r) => Object.values(r).map(String));

  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  // Title
  doc.setFontSize(14);
  doc.setTextColor(30, 30, 30);
  doc.text("F&O Signals Report", doc.internal.pageSize.getWidth() / 2, 32, { align: "center" });
  doc.setFontSize(8);
  doc.setTextColor(90, 90, 90);
  doc.text(`Generated: ${DATE_LABEL}`, 40, 52);

  autoTable(doc, {
    startY: 62,
    head: [headers],
    body,
    styles: { fontSize: 7, cellPadding: 3, overflow: "linebreak" },
    headStyles: { fillColor: [15, 23, 42], textColor: [148, 226, 213], fontStyle: "bold" },
    alternateRowStyles: { fillColor: [241, 245, 249] },
    columnStyles: {
      0: { cellWidth: 68 },
      1: { cellWidth: 38 },
      2: { cellWidth: 28 },
      3: { cellWidth: 40 },
      4: { cellWidth: 38 },
      5: { cellWidth: 38 },
      6: { cellWidth: 38 },
      7: { cellWidth: 52 },
      8: { cellWidth: 30 },
      9: { cellWidth: 50 },
      10: { cellWidth: 30 },
      11: { cellWidth: 50 },
      12: { cellWidth: 30 },
      13: { cellWidth: 42 },
    },
    didDrawPage: (data) => {
      // Footer note on each page
      const pageHeight = doc.internal.pageSize.getHeight();
      doc.setFontSize(6);
      doc.setTextColor(120, 120, 120);
      doc.text(NOTE, 40, pageHeight - 14);
    },
  });

  doc.save(`FnO_Signals_${FILE_DATE}.pdf`);
};

/** Export F&O data as Word (.docx) */
export const exportFnoAsWord = async (fnoData) => {
  const signals = collectAllFnoSignals(fnoData);
  if (!signals.length) return;
  const rows = signals.map(buildExportRow);
  const headers = Object.keys(rows[0]);

  const borderStyle = { style: "single", size: 4, color: "334155" };
  const cellBorder = { top: borderStyle, bottom: borderStyle, left: borderStyle, right: borderStyle };
  const shading = { fill: "0F172A" };

  const headerRow = new TableRow({
    children: headers.map((h) =>
      new TableCell({
        shading,
        borders: cellBorder,
        width: { size: Math.floor(9000 / headers.length), type: WidthType.DXA },
        children: [
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: h, bold: true, color: "94E2D5", size: 16 })],
          }),
        ],
      })
    ),
  });

  const dataRows = rows.map((row, i) =>
    new TableRow({
      children: Object.values(row).map((val) =>
        new TableCell({
          shading: i % 2 === 0 ? undefined : { fill: "F8FAFC" },
          borders: cellBorder,
          width: { size: Math.floor(9000 / headers.length), type: WidthType.DXA },
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: String(val ?? ""), size: 15 })],
            }),
          ],
        })
      ),
    })
  );

  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({
            heading: HeadingLevel.HEADING_1,
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: "F&O Signals Report", bold: true, size: 28, color: "0F172A" })],
          }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: `Generated: ${DATE_LABEL}`, size: 18, color: "64748B" })],
          }),
          new Paragraph({ children: [new TextRun({ text: "" })] }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [headerRow, ...dataRows],
          }),
          new Paragraph({ children: [new TextRun({ text: "" })] }),
          new Paragraph({
            children: [new TextRun({ text: NOTE, size: 14, color: "94A3B8", italics: true })],
          }),
        ],
      },
    ],
  });

  const buffer = await Packer.toBlob(doc);
  const url = URL.createObjectURL(buffer);
  const a = document.createElement("a");
  a.href = url;
  a.download = `FnO_Signals_${FILE_DATE}.docx`;
  a.click();
  URL.revokeObjectURL(url);
};
