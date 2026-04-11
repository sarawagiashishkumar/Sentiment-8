import { BarChart3, TrendingUp, FileUp, LayoutGrid } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function HomeDashboard({ setCurrentPage }) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6" data-testid="home-landing-dashboard">
      <h2 className="mb-6 text-2xl font-bold text-white">Landing Dashboard</h2>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Card className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400" onClick={() => setCurrentPage("multibagger")} data-testid="home-module-multibagger">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-cyan-300">
              <BarChart3 size={18} /> Multibagger
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-300">Discover potential multibagger stocks with RSI, GTT buy levels, and projected upside tables.</p>
          </CardContent>
        </Card>

        <Card className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400" onClick={() => setCurrentPage("fno")} data-testid="home-module-fno">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-cyan-300">
              <TrendingUp size={18} /> F&O Projections
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-300">Run live NIFTY/BANKNIFTY projections with assured vs non-directional strategy separation.</p>
          </CardContent>
        </Card>

        <Card className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400" onClick={() => setCurrentPage("portfolio")} data-testid="home-module-portfolio">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-cyan-300">
              <FileUp size={18} /> Portfolio Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-300">Upload holdings or enter manually to get per-stock upside/downside horizon analysis.</p>
          </CardContent>
        </Card>

        <Card className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400" onClick={() => setCurrentPage("heatmap")} data-testid="home-module-heatmap">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-cyan-300">
              <LayoutGrid size={18} /> Market Heatmap
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-300">Real-time sector, stock, and options heatmaps with live data, treemap visualizations, and sector drill-down.</p>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
