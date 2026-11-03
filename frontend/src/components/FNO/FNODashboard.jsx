import { useEffect, useRef, useState } from "react";
import { Download, RefreshCw, Settings } from "lucide-react";
import { Badge } from "components/ui/badge";
import { Button } from "components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "components/ui/card";
import { Input } from "components/ui/input";
import { formatNumber, formatTime } from "utils/formatters";
import { exportFnoAsCSV, exportFnoAsXLS, exportFnoAsJPG, exportFnoAsPDF, exportFnoAsWord } from "utils/exportUtils";
import { LiveInfoBox } from "components/shared/LiveInfoBox";
import { FNOSignalCard } from "./FNOSignalCard";
import { FNOStickyCards } from "./FNOStickyCards";
import { FNOEventPopup } from "./FNOEventPopup";
import { FNOSignalHistory } from "./FNOSignalHistory";
import { FNOIVAnalytics } from "./FNOIVAnalytics";
import { FNOMultiTimeframe } from "./FNOMultiTimeframe";
import { BBEAlertMonitor } from "./BBEAlertMonitor";
import { TradingJournal } from "./TradingJournal";
import { StrategyBacktester } from "./StrategyBacktester";
import { AlertRuleEngine } from "./AlertRuleEngine";
import { FNOExportTable } from "./FNOExportTable";
import { SubTabs } from "components/Layout/SubTabs";
import { useFNOGeneration } from "hooks/useFNOGeneration";
import axios from "axios";

const API = "/api";

const FNO_TABS = [
  { id: "signals", label: "Custom Script & F&O Generation" },
  { id: "alerts", label: "Alert Rules" },
  { id: "journal", label: "Trading Journal" },
  { id: "backtester", label: "Strategy Backtester" },
  { id: "performance", label: "Signal Performance Tracking" },
  { id: "analytics", label: "IV Analytics & Multi-Timeframe" },
];

export function FNODashboard({
  authHeaders, syncCredits, me, setMe,
  customPositions, loadCustomPositions,
  alertSoundEnabled, enableAlertSound, playAlertSound,
}) {
  const { fnoData, fnoLoading, fnoError, fnoProgress, generate } = useFNOGeneration({ authHeaders, syncCredits });
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportTableRef = useRef(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [budgetInput, setBudgetInput] = useState(String(me?.fno_budget || 500000));
  const [riskInput, setRiskInput] = useState(String(me?.account_risk_pct || 2.0));
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [activeTab, setActiveTab] = useState("signals");

  const saveSettings = async () => {
    const budget = Number(budgetInput);
    const risk = Number(riskInput);
    if (!budget || budget < 0 || !risk || risk <= 0 || risk > 100) return;
    setSettingsSaving(true);
    try {
      await axios.patch(`${API}/auth/settings`, { fno_budget: budget, account_risk_pct: risk }, { headers: authHeaders });
      setMe((prev) => prev ? { ...prev, fno_budget: budget, account_risk_pct: risk } : prev);
      setSettingsOpen(false);
    } catch (err) { console.error("Settings save failed:", err?.message); }
    finally { setSettingsSaving(false); }
  };

  useEffect(() => {
    if (!exportMenuOpen) return;
    const handler = (e) => {
      if (!e.target.closest("[data-testid='fno-export-btn']") && !e.target.closest("[data-testid='fno-export-menu']")) setExportMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportMenuOpen]);

  return (
    <section className="space-y-4" data-testid="fno-page">
      <SubTabs tabs={FNO_TABS} active={activeTab} onChange={setActiveTab} />

      {activeTab === "signals" && (
        <>
          <FNOGeneratorPanel
            me={me} fnoData={fnoData} fnoLoading={fnoLoading} fnoError={fnoError} fnoProgress={fnoProgress}
            generate={generate} settingsOpen={settingsOpen} setSettingsOpen={setSettingsOpen}
            budgetInput={budgetInput} setBudgetInput={setBudgetInput} riskInput={riskInput} setRiskInput={setRiskInput}
            settingsSaving={settingsSaving} saveSettings={saveSettings}
            exportMenuOpen={exportMenuOpen} setExportMenuOpen={setExportMenuOpen} exportTableRef={exportTableRef}
            customPositions={customPositions} loadCustomPositions={loadCustomPositions}
            authHeaders={authHeaders} syncCredits={syncCredits}
            alertSoundEnabled={alertSoundEnabled} enableAlertSound={enableAlertSound} playAlertSound={playAlertSound}
          />
          {fnoData && <FNOResultsGrid fnoData={fnoData} />}
          <FNOExportTable ref={exportTableRef} fnoData={fnoData} />
        </>
      )}

      {activeTab === "alerts" && <AlertRuleEngine authHeaders={authHeaders} />}
      {activeTab === "journal" && <TradingJournal authHeaders={authHeaders} />}
      {activeTab === "backtester" && <StrategyBacktester authHeaders={authHeaders} />}
      {activeTab === "performance" && <FNOSignalHistory authHeaders={authHeaders} />}
      {activeTab === "analytics" && (
        <div className="space-y-6">
          <FNOIVAnalytics authHeaders={authHeaders} />
          <FNOMultiTimeframe authHeaders={authHeaders} />
        </div>
      )}
    </section>
  );
}

// ── Signal Generator Panel ────────────────────────────────────────────────────

function FNOGeneratorPanel({
  me, fnoData, fnoLoading, fnoError, fnoProgress, generate,
  settingsOpen, setSettingsOpen, budgetInput, setBudgetInput, riskInput, setRiskInput,
  settingsSaving, saveSettings, exportMenuOpen, setExportMenuOpen, exportTableRef,
  customPositions, loadCustomPositions, authHeaders, syncCredits,
  alertSoundEnabled, enableAlertSound, playAlertSound,
}) {
  return (
    <Card className="result-card border-slate-800 bg-slate-950/70">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <div className="flex items-center gap-2">
          <CardTitle className="text-white">F&O Projections</CardTitle>
          <Button type="button" variant="ghost" size="sm" onClick={() => setSettingsOpen((v) => !v)} className="h-7 w-7 p-0 text-slate-400 hover:text-cyan-300" data-testid="fno-settings-toggle">
            <Settings size={15} />
          </Button>
          <span className="text-xs text-slate-500" data-testid="fno-budget-display">Budget: {Number(me?.fno_budget || 500000).toLocaleString("en-IN")} | Risk: {me?.account_risk_pct || 2}%</span>
        </div>
        <Button type="button" onClick={() => generate()} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="fno-generate-button">
          <RefreshCw size={16} className={fnoLoading ? "animate-spin" : ""} />
          {fnoLoading ? (fnoProgress || "Generating...") : "Generate F&O Projections (-2)"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {settingsOpen && (
          <div className="flex flex-wrap items-end gap-3 rounded-md border border-slate-700 bg-slate-900/80 p-3" data-testid="fno-settings-panel">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-400">Account Size</label>
              <Input type="number" min="0" step="1000" value={budgetInput} onChange={(e) => setBudgetInput(e.target.value)} className="w-40 border-slate-700 bg-slate-800 text-slate-100" data-testid="fno-budget-input" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-slate-400">Risk Per Trade (%)</label>
              <Input type="number" min="0.1" max="100" step="0.1" value={riskInput} onChange={(e) => setRiskInput(e.target.value)} className="w-28 border-slate-700 bg-slate-800 text-slate-100" data-testid="fno-risk-input" />
            </div>
            <Button type="button" onClick={saveSettings} disabled={settingsSaving} className="h-9 bg-cyan-600 text-white hover:bg-cyan-500" data-testid="fno-settings-save">
              {settingsSaving ? "Saving..." : "Save"}
            </Button>
          </div>
        )}
        <FNOStickyCards customPositions={customPositions} loadCustomPositions={loadCustomPositions} authHeaders={authHeaders} syncCredits={syncCredits} alertSoundEnabled={alertSoundEnabled} enableAlertSound={enableAlertSound} playAlertSound={playAlertSound} />
        <FNOEventPopup authHeaders={authHeaders} />
        <BBEAlertMonitor authHeaders={authHeaders} alertSoundEnabled={alertSoundEnabled} playAlertSound={playAlertSound} />
        {fnoError && <p className="text-sm text-rose-400" data-testid="fno-error">{fnoError}</p>}
        {!fnoData ? (
          <p className="text-sm text-slate-400" data-testid="fno-empty-note">Nothing shown yet. Click <strong>Generate F&O Projections (-2)</strong> for live analysis.</p>
        ) : (
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <p className="text-xs text-slate-400" data-testid="fno-refreshed-at">
              Refreshed at: {formatTime(fnoData.analysis_refreshed_at)} | Charged: {fnoData.cost_charged}
            </p>
            <ExportMenu fnoData={fnoData} open={exportMenuOpen} setOpen={setExportMenuOpen} exportTableRef={exportTableRef} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ExportMenu({ fnoData, open, setOpen, exportTableRef }) {
  const items = [
    { label: "Export as CSV", ext: "csv", fn: () => exportFnoAsCSV(fnoData) },
    { label: "Export as XLS", ext: "xls", fn: () => exportFnoAsXLS(fnoData) },
    { label: "Export as PDF", ext: "pdf", fn: () => exportFnoAsPDF(fnoData) },
    { label: "Export as Word", ext: "doc", fn: () => exportFnoAsWord(fnoData) },
    { label: "Export as JPG", ext: "jpg", fn: () => exportFnoAsJPG(exportTableRef) },
  ];
  return (
    <div className="relative">
      <Button data-testid="fno-export-btn" variant="outline" size="sm" className="border-cyan-700 bg-cyan-900/30 text-cyan-300 hover:bg-cyan-800/50 gap-1.5" onClick={() => setOpen((v) => !v)}>
        <Download className="h-3.5 w-3.5" /> Export
      </Button>
      {open && (
        <div className="absolute right-0 top-9 z-50 flex flex-col gap-0.5 rounded-lg border border-cyan-800 bg-slate-900 p-1 shadow-xl" data-testid="fno-export-menu">
          {items.map(({ label, ext, fn }) => (
            <button key={ext} data-testid={`export-${ext}`} className="flex items-center gap-2 rounded px-4 py-2 text-sm text-slate-200 hover:bg-cyan-900/50 hover:text-white whitespace-nowrap" onClick={() => { setOpen(false); fn(); }}>
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Results Grid ──────────────────────────────────────────────────────────────

function FNOResultsGrid({ fnoData }) {
  return (
    <>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3" data-testid="fno-3col-layout">
        <div className="lg:sticky lg:top-4 lg:self-start">
          {fnoData.nifty_projection ? <IndexPane pane={fnoData.nifty_projection} /> : <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-400 animate-pulse">Computing NIFTY...</div>}
        </div>
        <div>
          {fnoData.banknifty_projection ? <IndexPane pane={fnoData.banknifty_projection} /> : <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-400 animate-pulse">Computing BANKNIFTY...</div>}
        </div>
        <div className="space-y-4">
          <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="top4-trades-panel">
            <CardHeader className="py-3"><CardTitle className="text-white text-sm">Top 4 Best Stock Trades</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {fnoData.stock_signals?.length ? (
                [...fnoData.stock_signals].sort((a, b) => (b.confluence_score || 0) - (a.confluence_score || 0)).slice(0, 4).map((trade, idx) => (
                  <FNOSignalCard key={trade.script} signal={trade} suffix={`top4-${idx}`} variant="top4" />
                ))
              ) : <p className="text-sm text-slate-400">No stock trades available yet.</p>}
            </CardContent>
          </Card>
          {fnoData.custom_signal && (
            <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="custom-script-result-card">
              <CardHeader className="py-3"><CardTitle className="text-white text-sm">Custom Script Result</CardTitle></CardHeader>
              <CardContent className="space-y-1 text-xs">
                <p className="font-mono text-cyan-200">{fnoData.custom_signal.script}</p>
                <LiveInfoBox signal={fnoData.custom_signal} suffix="custom-script-result" />
                <p>Direction: {fnoData.custom_signal.direction}</p>
                <p>Entry/SL/T1/T2: {formatNumber(fnoData.custom_signal.entry_price)} / {formatNumber(fnoData.custom_signal.stop_loss)} / {formatNumber(fnoData.custom_signal.target1)} / {formatNumber(fnoData.custom_signal.target2)}</p>
                <p>Confluence: {fnoData.custom_signal.confluence_score}</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
      <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="stock-fno-bottom-panel">
        <CardHeader><CardTitle className="text-white">Profitable F&O Signals — Best 15 Individual Stocks</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {fnoData.stock_signals?.length ? (
            fnoData.stock_signals.slice(0, 15).map((signal, idx) => <FNOSignalCard key={signal.script} signal={signal} suffix={`stock-${idx}`} variant="stock" />)
          ) : <p className="text-sm text-slate-400" data-testid="stock-fno-empty-note">No verified stock option-chain opportunities found in this cycle.</p>}
        </CardContent>
      </Card>
    </>
  );
}

// ── Index Pane (NIFTY / BANKNIFTY) ───────────────────────────────────────────

function IndexPane({ pane }) {
  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid={`pane-${pane.index_name.toLowerCase()}`}>
      <CardHeader className="py-3">
        <CardTitle className="flex items-center justify-between gap-2 text-white text-sm">
          <span>{pane.index_name}</span>
          <Badge className="border border-cyan-500/50 bg-cyan-500/20 text-cyan-200 text-xs">Spot {formatNumber(pane.spot, 2)}</Badge>
        </CardTitle>
        <p className="text-[10px] text-slate-400">Strike: {formatNumber(pane.strike_range_min, 0)} – {formatNumber(pane.strike_range_max, 0)}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <SignalSection title="Assured Directional" signals={pane.assured_signals} prefix={`assured-${pane.index_name.toLowerCase()}`} variant="assured" color="cyan" />
        <SignalSection title="Watchlist" signals={pane.watchlist_signals} prefix={`watch-${pane.index_name.toLowerCase()}`} variant="watchlist" color="emerald" />
        <NonDirectionalSection strategies={pane.non_directional_strategies} indexName={pane.index_name} />
        <ReportsSection pane={pane} />
        {pane.rejection_note && <p className="rounded-md border border-slate-700 bg-slate-900/70 p-2 text-[10px] font-bold text-white">{pane.rejection_note}</p>}
      </CardContent>
    </Card>
  );
}

function SignalSection({ title, signals, prefix, variant, color }) {
  const colorMap = { cyan: "text-cyan-300", emerald: "text-emerald-300" };
  return (
    <div>
      <p className={`mb-1.5 text-xs font-semibold ${colorMap[color]}`}>{title}</p>
      {signals?.length ? (
        <div className="space-y-1.5">{signals.slice(0, 4).map((s, i) => <FNOSignalCard key={s.script} signal={s} suffix={`${prefix}-${i}`} variant={variant} />)}</div>
      ) : <p className="text-[10px] text-slate-500">No {title.toLowerCase()} setups right now.</p>}
    </div>
  );
}

function NonDirectionalSection({ strategies, indexName }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold text-amber-300">Non-Directional</p>
      {strategies?.length ? (
        <div className="space-y-1.5">
          {strategies.map((item) => (
            <div key={`${indexName}-${item.strike}`} className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[10px]">
              <p className="font-semibold text-amber-200">{item.strategy}</p>
              <p>Strike: {formatNumber(item.strike, 0)} | CE: {item.ce_script} | PE: {item.pe_script}</p>
              <p>Entry: {formatNumber(item.combined_entry)}</p>
            </div>
          ))}
        </div>
      ) : <p className="text-[10px] text-slate-500">No non-directional setups.</p>}
    </div>
  );
}

function ReportsSection({ pane }) {
  return (
    <div className="space-y-1.5">
      {["with_consolidated_report", "without_consolidated_report"].map(key => {
        const r = pane[key];
        const label = key.includes("with") ? "With Consolidated" : "Without Consolidated";
        return (
          <div key={key} className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-[10px]">
            <p className="font-semibold text-cyan-300 mb-0.5">{label}</p>
            <p>Breadth: {formatNumber(r.breadth_score)} | Momentum: {formatNumber(r.momentum_score)} | Bias: {r.bias}</p>
          </div>
        );
      })}
    </div>
  );
}
