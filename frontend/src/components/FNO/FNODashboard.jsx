import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber, formatTime, formatExpiryDate, directionBadge } from "@/utils/formatters";
import { collectAllFnoSignals, buildExportRow, exportFnoAsCSV, exportFnoAsXLS, exportFnoAsJPG, exportFnoAsPDF, exportFnoAsWord } from "@/utils/exportUtils";
import { readNDJSONStream } from "@/components/Shared/NDJSONStreamConsumer";
import { LiveInfoBox } from "@/components/shared/LiveInfoBox";
import { FNOSignalCard } from "./FNOSignalCard";
import { FNOStickyCards } from "./FNOStickyCards";
import { FNOEventPopup } from "./FNOEventPopup";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function FNODashboard({
  authHeaders, syncCredits, me,
  customPositions, loadCustomPositions,
  alertSoundEnabled, enableAlertSound, playAlertSound,
}) {
  const [fnoData, setFnoData] = useState(null);
  const [fnoLoading, setFnoLoading] = useState(false);
  const [fnoError, setFnoError] = useState("");
  const [fnoProgress, setFnoProgress] = useState("");
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportTableRef = useRef(null);

  // Close export menu on outside click
  useEffect(() => {
    if (!exportMenuOpen) return;
    const handler = (e) => {
      if (!e.target.closest("[data-testid='fno-export-btn']") && !e.target.closest("[data-testid='fno-export-menu']")) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportMenuOpen]);

  const generateFnoProjection = async (script = "") => {
    setFnoError("");
    setFnoLoading(true);
    setFnoProgress("");
    try {
      const payload = script ? { custom_script: script.trim().toUpperCase() } : {};
      const response = await fetch(`${API}/fno/generate`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }
      const data = await readNDJSONStream(response, (evt) => setFnoProgress(evt.message || ""));
      if (data) {
        setFnoData(data);
        syncCredits(data.credits_remaining);
      }
    } catch (error) {
      setFnoError(error?.message || "Unable to generate F&O projections");
    } finally {
      setFnoLoading(false);
      setFnoProgress("");
    }
  };

  return (
    <section className="space-y-6" data-testid="fno-page">
      <Card className="result-card border-slate-800 bg-slate-950/70">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <CardTitle className="text-white">F&O Projections</CardTitle>
          <Button type="button" onClick={() => generateFnoProjection()} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="fno-generate-button">
            <RefreshCw size={16} className={fnoLoading ? "animate-spin" : ""} />
            {fnoLoading ? (fnoProgress || "Generating...") : "Generate F&O Projections (-2)"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <FNOStickyCards
            customPositions={customPositions}
            loadCustomPositions={loadCustomPositions}
            authHeaders={authHeaders}
            syncCredits={syncCredits}
            alertSoundEnabled={alertSoundEnabled}
            enableAlertSound={enableAlertSound}
            playAlertSound={playAlertSound}
          />

          <FNOEventPopup authHeaders={authHeaders} />

          {fnoError ? <p className="text-sm text-rose-400" data-testid="fno-error">{fnoError}</p> : null}
          {!fnoData ? (
            <p className="text-sm text-slate-400" data-testid="fno-empty-note">
              Nothing shown yet. Click <strong>Generate F&O Projections (-2)</strong> for live analysis.
            </p>
          ) : (
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <p className="text-xs text-slate-400" data-testid="fno-refreshed-at">
                Refreshed at: {formatTime(fnoData.analysis_refreshed_at)} | Charged: {fnoData.cost_charged}
              </p>
              {/* Export Results Button */}
              <div className="relative">
                <Button data-testid="fno-export-btn" variant="outline" size="sm" className="border-cyan-700 bg-cyan-900/30 text-cyan-300 hover:bg-cyan-800/50 gap-1.5" onClick={() => setExportMenuOpen((v) => !v)}>
                  <Download className="h-3.5 w-3.5" />
                  Export Results
                </Button>
                {exportMenuOpen && (
                  <div className="absolute right-0 top-9 z-50 flex flex-col gap-0.5 rounded-lg border border-cyan-800 bg-slate-900 p-1 shadow-xl" data-testid="fno-export-menu">
                    {[
                      { label: "Export as CSV", ext: "csv", icon: "\ud83d\udcc4", testid: "export-csv" },
                      { label: "Export as XLS", ext: "xls", icon: "\ud83d\udcca", testid: "export-xls" },
                      { label: "Export as PDF", ext: "pdf", icon: "\ud83d\udcd1", testid: "export-pdf" },
                      { label: "Export as Word", ext: "doc", icon: "\ud83d\udcdd", testid: "export-doc" },
                      { label: "Export as JPG", ext: "jpg", icon: "\ud83d\uddbc", testid: "export-jpg" },
                    ].map(({ label, ext, icon, testid }) => (
                      <button
                        key={ext}
                        data-testid={testid}
                        className="flex items-center gap-2 rounded px-4 py-2 text-sm text-slate-200 hover:bg-cyan-900/50 hover:text-white transition-colors whitespace-nowrap"
                        onClick={() => {
                          setExportMenuOpen(false);
                          if (ext === "csv") exportFnoAsCSV(fnoData);
                          else if (ext === "xls") exportFnoAsXLS(fnoData);
                          else if (ext === "pdf") exportFnoAsPDF(fnoData);
                          else if (ext === "doc") exportFnoAsWord(fnoData);
                          else exportFnoAsJPG(exportTableRef);
                        }}
                      >
                        <span>{icon}</span>
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {fnoData ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <div className="space-y-6 xl:col-span-8">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2" data-testid="fno-dual-pane">
              {[fnoData.nifty_projection, fnoData.banknifty_projection].map((pane) => (
                <Card key={pane.index_name} className="result-card border-slate-800 bg-slate-950/70" data-testid={`pane-${pane.index_name.toLowerCase()}`}>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between gap-2 text-white">
                      <span>{pane.index_name}</span>
                      <Badge className="border border-cyan-500/50 bg-cyan-500/20 text-cyan-200">Spot {formatNumber(pane.spot, 2)}</Badge>
                    </CardTitle>
                    <p className="text-xs text-slate-400" data-testid={`pane-range-${pane.index_name.toLowerCase()}`}>
                      Strike Filter: {formatNumber(pane.strike_range_min, 0)} to {formatNumber(pane.strike_range_max, 0)}
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Assured Signals */}
                    <div data-testid={`pane-assured-${pane.index_name.toLowerCase()}`}>
                      <p className="mb-2 text-sm font-semibold text-cyan-300">Assured Directional Projections</p>
                      {pane.assured_signals.length ? (
                        <div className="space-y-2">
                          {pane.assured_signals.slice(0, 5).map((signal, idx) => (
                            <FNOSignalCard key={signal.script} signal={signal} suffix={`assured-${pane.index_name.toLowerCase()}-${idx}`} variant="assured" />
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400">No assured directional setup currently.</p>
                      )}
                    </div>

                    {/* Watchlist Signals */}
                    <div data-testid={`pane-watchlist-${pane.index_name.toLowerCase()}`}>
                      <p className="mb-2 text-sm font-semibold text-emerald-300">Watchlist (Medium Conviction)</p>
                      {pane.watchlist_signals?.length ? (
                        <div className="space-y-2">
                          {pane.watchlist_signals.map((signal, idx) => (
                            <FNOSignalCard key={`${signal.script}-watch`} signal={signal} suffix={`watch-${pane.index_name.toLowerCase()}-${idx}`} variant="watchlist" />
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400">No medium-conviction watchlist setup right now.</p>
                      )}
                    </div>

                    {/* Non-Directional Strategies */}
                    <div data-testid={`pane-nondirectional-${pane.index_name.toLowerCase()}`}>
                      <p className="mb-2 text-sm font-semibold text-amber-300">Non-Directional Strategies</p>
                      {pane.non_directional_strategies.length ? (
                        <div className="space-y-2">
                          {pane.non_directional_strategies.map((item) => (
                            <div key={`${pane.index_name}-${item.strike}`} className="result-hover rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs">
                              <p className="font-semibold text-amber-200">{item.strategy}</p>
                              <p>Strike: {formatNumber(item.strike, 0)} | CE: {item.ce_script} | PE: {item.pe_script}</p>
                              <p>Combined Entry: ₹{formatNumber(item.combined_entry)}</p>
                              <p>{item.rationale}</p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400">No CE+PE same-strike conflict currently.</p>
                      )}
                    </div>

                    {/* Reports */}
                    <div className="grid grid-cols-1 gap-2" data-testid={`pane-reports-${pane.index_name.toLowerCase()}`}>
                      <div className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                        <p className="font-semibold text-cyan-300">With Consolidated Analysis</p>
                        <p>Breadth: {formatNumber(pane.with_consolidated_report.breadth_score)} | Momentum: {formatNumber(pane.with_consolidated_report.momentum_score)} | Bias: {pane.with_consolidated_report.bias}</p>
                        <p>Contributors: {pane.with_consolidated_report.top_contributors.join(" | ")}</p>
                      </div>
                      <div className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                        <p className="font-semibold text-cyan-300">Without Consolidated Analysis</p>
                        <p>Breadth: {formatNumber(pane.without_consolidated_report.breadth_score)} | Momentum: {formatNumber(pane.without_consolidated_report.momentum_score)} | Bias: {pane.without_consolidated_report.bias}</p>
                        <p>Contributors: {pane.without_consolidated_report.top_contributors.join(" | ")}</p>
                      </div>
                    </div>

                    {pane.rejection_note ? (
                      <p className="rounded-md border border-slate-700 bg-slate-900/70 p-2 text-xs font-bold text-white transition-colors hover:text-blue-900" data-testid={`pane-rejection-note-${pane.index_name.toLowerCase()}`}>
                        {pane.rejection_note}
                      </p>
                    ) : null}
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Stock Signals */}
            <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="stock-fno-bottom-panel">
              <CardHeader>
                <CardTitle className="text-white">Profitable F&O Signals — Individual Stocks</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {fnoData.stock_signals?.length ? (
                  fnoData.stock_signals.map((signal, idx) => (
                    <FNOSignalCard key={signal.script} signal={signal} suffix={`stock-${idx}`} variant="stock" />
                  ))
                ) : (
                  <p className="text-sm text-slate-400" data-testid="stock-fno-empty-note">No verified stock option-chain opportunities found in this cycle.</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar: Top 4 + Custom Script */}
          <div className="xl:col-span-4">
            <div className="sticky top-4 space-y-4">
              <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="top4-trades-panel">
                <CardHeader>
                  <CardTitle className="text-white">Top 4 Best Trade Now</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {fnoData.top_trades?.length ? (
                    fnoData.top_trades.map((trade, idx) => (
                      <FNOSignalCard key={trade.script} signal={trade} suffix={`top4-${idx}`} variant="top4" />
                    ))
                  ) : (
                    <p className="text-sm text-slate-400">Generate projections to populate Top 4 trades.</p>
                  )}
                </CardContent>
              </Card>

              {fnoData.custom_signal ? (
                <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="custom-script-result-card">
                  <CardHeader>
                    <CardTitle className="text-white">Custom Script Result</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 text-xs">
                    <p className="font-mono text-cyan-200">{fnoData.custom_signal.script}</p>
                    <LiveInfoBox signal={fnoData.custom_signal} suffix="custom-script-result" />
                    <p>Direction: {fnoData.custom_signal.direction}</p>
                    <p>Entry/SL/T1/T2: ₹{formatNumber(fnoData.custom_signal.entry_price)} / ₹{formatNumber(fnoData.custom_signal.stop_loss)} / ₹{formatNumber(fnoData.custom_signal.target1)} / ₹{formatNumber(fnoData.custom_signal.target2)}</p>
                    <p>Confluence: {fnoData.custom_signal.confluence_score >= 80 ? "\u2b50 " : ""}{fnoData.custom_signal.confluence_score}</p>
                  </CardContent>
                </Card>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {/* Hidden Export Table for JPG capture */}
      {fnoData && (
        <div
          ref={exportTableRef}
          style={{
            position: "absolute", left: "-9999px", top: 0, width: "1100px",
            background: "#ffffff", padding: "24px", fontFamily: "Arial, sans-serif", fontSize: "13px", color: "#1a1a1a",
          }}
        >
          <h2 style={{ fontSize: "16px", fontWeight: "bold", marginBottom: "8px", color: "#FFFFFF", background: "#1E3A5F", padding: "8px 12px", borderRadius: "4px" }}>
            Stock Options — Correct Lot Sizes \u0915\u0947 \u0938\u093e\u0925
          </h2>
          <table style={{ width: "100%", borderCollapse: "collapse", color: "#1A1A1A" }}>
            <thead>
              <tr style={{ background: "#1E3A5F" }}>
                {["Script", "Bias", "Lot", "Entry ₹", "SL", "T1", "T2", "Investment (₹)", "T1%", "T1 Profit ₹", "T2%", "T2 Profit ₹", "Conf", "Bias Point"].map((h) => (
                  <th key={h} style={{ border: "1px solid #d1d5db", padding: "6px 8px", textAlign: "center", fontWeight: "600", fontSize: "12px", color: "#FFFFFF" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {collectAllFnoSignals(fnoData).map((sig, i) => {
                const row = buildExportRow(sig);
                return (
                  <tr key={sig.script} style={{ background: i % 2 === 0 ? "#ffffff" : "#f0f4f8", color: "#1A1A1A" }}>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", fontWeight: "500", color: "#1A1A1A" }}>{row["Script"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "center", color: row["Bias"] === "BULLISH" ? "#059669" : "#dc2626", fontWeight: "600" }}>{row["Bias"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>{row["Lot"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>₹{row["Entry ₹"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#dc2626" }}>{row["SL"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>{row["T1"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>{row["T2"]}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>₹{Number(row["Investment (₹)"]).toLocaleString("en-IN")}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T1%"]).toFixed(2)}%</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>₹{Number(row["T1 Profit ₹"]).toLocaleString("en-IN")}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T2%"]).toFixed(2)}%</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>₹{Number(row["T2 Profit ₹"]).toLocaleString("en-IN")}</td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "center", fontWeight: "600", color: row["Conf"] >= 80 ? "#D97706" : "#1A1A1A" }}>
                      {row["Conf"] >= 80 ? "\u2b50 " : ""}{row["Conf"]}
                    </td>
                    <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: row["Bias Point"] >= 0 ? "#2563EB" : "#EA580C" }}>{Number(row["Bias Point"]).toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={{ marginTop: "12px", fontSize: "11px", color: "#6b7280" }}>
            Note: \u0938\u092d\u0940 lot sizes NSE verified \u0939\u0948\u0902 (March 2026 – dhan.co) — Investment = Entry Price × Lot Size (1 lot premium cost) | Generated: {new Date().toLocaleString("en-IN")}
          </p>
        </div>
      )}
    </section>
  );
}
