import { useState } from "react";
import { Grid3X3, BarChart3, Layers } from "lucide-react";
import { SubTabs } from "@/components/Layout/SubTabs";
import { SectorHeatmap } from "./SectorHeatmap";
import { StocksHeatmap } from "./StocksHeatmap";
import { OptionsHeatmap } from "./OptionsHeatmap";

const TABS = [
  { id: "sectors", label: "Sector Heatmap", icon: Grid3X3 },
  { id: "stocks", label: "Stocks Heatmap", icon: BarChart3 },
  { id: "options", label: "Options Heatmap", icon: Layers },
];

export function MarketHeatmapDashboard({ authHeaders }) {
  const [activeTab, setActiveTab] = useState("sectors");

  return (
    <section className="space-y-4" data-testid="market-heatmap-page">
      <SubTabs tabs={TABS} active={activeTab} onChange={setActiveTab} />
      {activeTab === "sectors" && <SectorHeatmap authHeaders={authHeaders} />}
      {activeTab === "stocks" && <StocksHeatmap authHeaders={authHeaders} />}
      {activeTab === "options" && <OptionsHeatmap authHeaders={authHeaders} />}
    </section>
  );
}
