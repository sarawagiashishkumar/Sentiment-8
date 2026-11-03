import { forwardRef } from "react";
import { formatNumber } from "utils/formatters";
import { collectAllFnoSignals, buildExportRow } from "utils/exportUtils";

export const FNOExportTable = forwardRef(function FNOExportTable({ fnoData }, ref) {
  if (!fnoData) return null;
  return (
    <div
      ref={ref}
      style={{
        position: "absolute", left: "-9999px", top: 0, width: "1100px",
        background: "#ffffff", padding: "24px", fontFamily: "Arial, sans-serif", fontSize: "13px", color: "#1a1a1a",
      }}
    >
      <h2 style={{ fontSize: "16px", fontWeight: "bold", marginBottom: "8px", color: "#FFFFFF", background: "#1E3A5F", padding: "8px 12px", borderRadius: "4px" }}>
        Stock Options — Correct Lot Sizes
      </h2>
      <table style={{ width: "100%", borderCollapse: "collapse", color: "#1A1A1A" }}>
        <thead>
          <tr style={{ background: "#1E3A5F" }}>
            {["Script", "Bias", "Lot", "Entry", "SL", "T1", "T2", "Investment", "T1%", "T1 Profit", "T2%", "T2 Profit", "Conf", "Bias Pt"].map((h) => (
              <th key={h} style={{ border: "1px solid #d1d5db", padding: "6px 8px", textAlign: "center", fontWeight: "600", fontSize: "12px", color: "#FFFFFF" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {collectAllFnoSignals(fnoData).map((sig, i) => {
            const row = buildExportRow(sig);
            return (
              <tr key={sig.script} style={{ background: i % 2 === 0 ? "#ffffff" : "#f0f4f8", color: "#1A1A1A" }}>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", fontWeight: "500" }}>{row["Script"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "center", color: row["Bias"] === "BULLISH" ? "#059669" : "#dc2626", fontWeight: "600" }}>{row["Bias"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right" }}>{row["Lot"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right" }}>{formatNumber(row["Entry ₹"])}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#dc2626" }}>{row["SL"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right" }}>{row["T1"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right" }}>{row["T2"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right" }}>{Number(row["Investment (₹)"]).toLocaleString("en-IN")}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T1%"]).toFixed(2)}%</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T1 Profit ₹"]).toLocaleString("en-IN")}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T2%"]).toFixed(2)}%</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T2 Profit ₹"]).toLocaleString("en-IN")}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "center", fontWeight: "600", color: row["Conf"] >= 80 ? "#D97706" : "#1A1A1A" }}>{row["Conf"]}</td>
                <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: row["Bias Point"] >= 0 ? "#2563EB" : "#EA580C" }}>{Number(row["Bias Point"]).toFixed(2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p style={{ marginTop: "12px", fontSize: "11px", color: "#6b7280" }}>
        Note: Lot sizes NSE verified (March 2026) — Investment = Entry Price x Lot Size | Generated: {new Date().toLocaleString("en-IN")}
      </p>
    </div>
  );
});
