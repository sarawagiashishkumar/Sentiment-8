import { useState, useCallback } from "react";
import { SubTabs } from "components/Layout/SubTabs";
import { SectorHeatmap } from "./SectorHeatmap";
import { StocksHeatmap } from "./StocksHeatmap";
import { OptionsHeatmap } from "./OptionsHeatmap";
import { DataFetchErrorPopup } from "components/Shared/KiteLiveWarning";

const TABS = [
  { id: "sectors", label: "Sector Heatmap" },
  { id: "stocks", label: "Stocks Heatmap" },
  { id: "options", label: "Options Heatmap" },
];

export function MarketHeatmapDashboard({ authHeaders }) {
  const [activeTab, setActiveTab] = useState("sectors");
  const [showFetchError, setShowFetchError] = useState(false);

  const handleFetchError = useCallback(() => {
    setShowFetchError(true);
  }, []);

  return (
    <section className="space-y-4" data-testid="market-heatmap-page">
      <SubTabs tabs={TABS} active={activeTab} onChange={setActiveTab} />
      {activeTab === "sectors" && <SectorHeatmap authHeaders={authHeaders} onFetchError={handleFetchError} />}
      {activeTab === "stocks" && <StocksHeatmap authHeaders={authHeaders} onFetchError={handleFetchError} />}
      {activeTab === "options" && <OptionsHeatmap authHeaders={authHeaders} onFetchError={handleFetchError} />}
      <DataFetchErrorPopup show={showFetchError} onClose={() => setShowFetchError(false)} />
    </section>
  );
}
