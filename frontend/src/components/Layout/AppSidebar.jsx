import { Home, BarChart3, TrendingUp, FileUp, Shield, Grid3X3, FileText, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AppSidebar({ currentPage, setCurrentPage, isAdmin, onAdminClick }) {
  const navClass = (page) =>
    currentPage === page
      ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400"
      : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800";

  return (
    <nav className="mb-4 -mx-1 px-1 overflow-x-auto scrollbar-hide" data-testid="persistent-nav">
      <div className="flex items-center gap-2 min-w-max pb-1">
        <Button type="button" onClick={() => setCurrentPage("home")} className={`text-xs shrink-0 ${navClass("home")}`} data-testid="nav-home">
          <Home size={14} /> Home
        </Button>
        <Button type="button" onClick={() => setCurrentPage("multibagger")} className={`text-xs shrink-0 ${navClass("multibagger")}`} data-testid="nav-multibagger">
          <BarChart3 size={14} /> <span className="hidden sm:inline">Multibagger</span><span className="sm:hidden">MB</span>
        </Button>
        <Button type="button" onClick={() => setCurrentPage("fno")} className={`text-xs shrink-0 ${navClass("fno")}`} data-testid="nav-fno-projections">
          <TrendingUp size={14} /> <span className="hidden sm:inline">F&O Projections</span><span className="sm:hidden">F&O</span>
        </Button>
        <Button type="button" onClick={() => setCurrentPage("portfolio")} className={`text-xs shrink-0 ${navClass("portfolio")}`} data-testid="nav-portfolio">
          <FileUp size={14} /> <span className="hidden sm:inline">Portfolio</span><span className="sm:hidden">Port</span>
        </Button>
        <Button type="button" onClick={() => setCurrentPage("heatmap")} className={`text-xs shrink-0 ${navClass("heatmap")}`} data-testid="nav-heatmap">
          <Grid3X3 size={14} /> <span className="hidden sm:inline">Market HeatMap</span><span className="sm:hidden">Heat</span>
        </Button>
        <Button type="button" onClick={() => setCurrentPage("reports")} className={`text-xs shrink-0 ${navClass("reports")}`} data-testid="nav-reports">
          <FileText size={14} /> <span className="hidden sm:inline">Reports</span><span className="sm:hidden">Rep</span>
        </Button>
        <Button type="button" onClick={() => setCurrentPage("watchlist")} className={`text-xs shrink-0 ${navClass("watchlist")}`} data-testid="nav-watchlist">
          <Eye size={14} /> <span className="hidden sm:inline">Watchlist</span><span className="sm:hidden">Watch</span>
        </Button>
        {isAdmin ? (
          <Button type="button" onClick={() => { setCurrentPage("admin"); onAdminClick(); }} className={`text-xs shrink-0 ${navClass("admin")}`} data-testid="nav-admin">
            <Shield size={14} /> Admin
          </Button>
        ) : null}
      </div>
    </nav>
  );
}
