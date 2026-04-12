import { Home, BarChart3, TrendingUp, FileUp, Shield, Grid3X3 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AppSidebar({ currentPage, setCurrentPage, isAdmin, onAdminClick }) {
  const navClass = (page) =>
    currentPage === page
      ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400"
      : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800";

  return (
    <nav className="mb-6 flex flex-wrap gap-2 sm:gap-3" data-testid="persistent-nav">
      <Button type="button" onClick={() => setCurrentPage("home")} className={`text-xs sm:text-sm ${navClass("home")}`} data-testid="nav-home">
        <Home size={14} /> <span className="hidden xs:inline">Home</span>
      </Button>
      <Button type="button" onClick={() => setCurrentPage("multibagger")} className={`text-xs sm:text-sm ${navClass("multibagger")}`} data-testid="nav-multibagger">
        <BarChart3 size={14} /> <span className="hidden sm:inline">Multibagger</span><span className="sm:hidden">MB</span>
      </Button>
      <Button type="button" onClick={() => setCurrentPage("fno")} className={`text-xs sm:text-sm ${navClass("fno")}`} data-testid="nav-fno-projections">
        <TrendingUp size={14} /> <span className="hidden sm:inline">F&O Projections</span><span className="sm:hidden">F&O</span>
      </Button>
      <Button type="button" onClick={() => setCurrentPage("portfolio")} className={`text-xs sm:text-sm ${navClass("portfolio")}`} data-testid="nav-portfolio">
        <FileUp size={14} /> <span className="hidden sm:inline">Portfolio</span><span className="sm:hidden">Port</span>
      </Button>
      <Button type="button" onClick={() => setCurrentPage("heatmap")} className={`text-xs sm:text-sm ${navClass("heatmap")}`} data-testid="nav-heatmap">
        <Grid3X3 size={14} /> <span className="hidden sm:inline">Market HeatMap</span><span className="sm:hidden">Heat</span>
      </Button>
      {isAdmin ? (
        <Button type="button" onClick={() => { setCurrentPage("admin"); onAdminClick(); }} className={`text-xs sm:text-sm ${navClass("admin")}`} data-testid="nav-admin">
          <Shield size={14} /> <span className="hidden sm:inline">Admin</span>
        </Button>
      ) : null}
    </nav>
  );
}
