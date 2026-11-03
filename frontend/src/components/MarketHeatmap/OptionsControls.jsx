import { Activity, LayoutGrid, List } from "lucide-react";
import { RefreshCountdown } from "components/Shared/RefreshCountdown";
import { OptionsSymbolSearch } from "./OptionsSymbolSearch";

const INDEX_TABS = [
  { id: "nifty", label: "NIFTY" },
  { id: "banknifty", label: "BANKNIFTY" },
];

const TOP_FNO_STOCKS = [
  { id: "RELIANCE", label: "RELIANCE" },
  { id: "TCS", label: "TCS" },
  { id: "HDFCBANK", label: "HDFCBANK" },
];

export function OptionsControls({
  activeSymbol, setActiveSymbol,
  oiTypeFilter, setOiTypeFilter,
  selectedExpiry, setSelectedExpiry,
  availableExpiries,
  minOI, setMinOI,
  viewMode, setViewMode,
  refreshIntervalMs, onManualRefresh,
}) {
  const isIndexTab = INDEX_TABS.some(t => t.id === activeSymbol);
  const isTopStock = TOP_FNO_STOCKS.some(t => t.id === activeSymbol);

  return (
    <>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" />
          Options Heatmap
        </h2>
        <RefreshCountdown intervalMs={refreshIntervalMs} isActive={true} onManualRefresh={onManualRefresh} />
      </div>

      {/* Row 1: NIFTY / BANKNIFTY Tabs + OI filter + Expiry */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="options-index-tabs">
        {INDEX_TABS.map(t => (
          <button key={t.id} data-testid={`options-tab-${t.id}`}
            onClick={() => setActiveSymbol(t.id)}
            className={`rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
              activeSymbol === t.id
                ? "bg-cyan-600 text-white shadow-lg shadow-cyan-500/20"
                : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700"
            }`}>{t.label}</button>
        ))}
        <div className="w-px h-5 bg-slate-700" />
        {["all", "ce", "pe"].map(t => (
          <button key={t} data-testid={`options-oi-type-${t}`}
            onClick={() => setOiTypeFilter(t)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              oiTypeFilter === t ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}>{t.toUpperCase()}</button>
        ))}
        <div className="w-px h-5 bg-slate-700" />
        {availableExpiries.length > 0 && (
          <select
            value={selectedExpiry}
            onChange={(e) => setSelectedExpiry(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-300 focus:border-cyan-500 focus:outline-none"
            data-testid="options-expiry-select"
          >
            <option value="">Nearest Expiry</option>
            {availableExpiries.map(exp => (
              <option key={exp} value={exp}>{exp}</option>
            ))}
          </select>
        )}
      </div>

      {/* Row 2: Top 3 F&O Stocks + Custom Search + Min OI + View Toggle */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="options-stock-filters">
        {TOP_FNO_STOCKS.map(f => (
          <button key={f.id} data-testid={`options-stock-${f.id.toLowerCase()}`}
            onClick={() => setActiveSymbol(f.id)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
              activeSymbol === f.id ? "bg-emerald-600 text-white" : "text-slate-400 hover:text-slate-200 bg-slate-800/50"
            }`}>{f.label}</button>
        ))}

        <OptionsSymbolSearch activeSymbol={activeSymbol} setActiveSymbol={setActiveSymbol} />

        {!isIndexTab && !isTopStock && activeSymbol && (
          <span className="rounded bg-violet-600 px-2 py-0.5 text-xs font-mono text-white" data-testid="options-active-custom">
            {activeSymbol}
          </span>
        )}

        <div className="flex items-center gap-1 text-[10px] text-slate-400 ml-auto">
          <Activity size={10} />
          <span>Min OI:</span>
          <input
            type="range" min="0" max="50000" step="1000" value={minOI}
            onChange={(e) => setMinOI(Number(e.target.value))}
            className="w-16 h-1 accent-cyan-500"
            data-testid="options-min-oi-slider"
          />
          <span className="font-mono text-slate-300 w-6 text-right">{minOI > 0 ? `${(minOI/1000).toFixed(0)}K` : "0"}</span>
        </div>

        <div className="flex border border-slate-700 rounded-md overflow-hidden">
          <button data-testid="options-view-treemap" onClick={() => setViewMode("treemap")}
            className={`p-1.5 ${viewMode === "treemap" ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
            <LayoutGrid size={13} />
          </button>
          <button data-testid="options-view-chain" onClick={() => setViewMode("chain")}
            className={`p-1.5 ${viewMode === "chain" ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"}`}>
            <List size={13} />
          </button>
        </div>
      </div>
    </>
  );
}
