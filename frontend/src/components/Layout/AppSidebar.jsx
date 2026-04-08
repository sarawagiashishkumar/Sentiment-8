import { Home, BarChart3, TrendingUp, FileUp, GaugeCircle, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AppSidebar({ currentPage, setCurrentPage, isAdmin, isOwner, onSectorClick, onAdminClick }) {
  const navClass = (page) =>
    currentPage === page
      ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400"
      : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800";

  return (
    <nav className="mb-6 flex flex-wrap gap-3" data-testid="persistent-nav">
      <Button type="button" onClick={() => setCurrentPage("home")} className={navClass("home")} data-testid="nav-home">
        <Home size={16} /> Home
      </Button>
      <Button type="button" onClick={() => setCurrentPage("multibagger")} className={navClass("multibagger")} data-testid="nav-multibagger">
        <BarChart3 size={16} /> Multibagger
      </Button>
      <Button type="button" onClick={() => setCurrentPage("fno")} className={navClass("fno")} data-testid="nav-fno-projections">
        <TrendingUp size={16} /> F&O Projections
      </Button>
      <Button type="button" onClick={() => setCurrentPage("portfolio")} className={navClass("portfolio")} data-testid="nav-portfolio">
        <FileUp size={16} /> Portfolio
      </Button>
      <Button type="button" onClick={() => { setCurrentPage("sectors"); onSectorClick(); }} className={navClass("sectors")} data-testid="nav-sectors">
        <GaugeCircle size={16} /> Sectors
      </Button>
      {isAdmin ? (
        <Button type="button" onClick={() => { setCurrentPage("admin"); onAdminClick(); }} className={navClass("admin")} data-testid="nav-admin">
          <Shield size={16} /> Admin
        </Button>
      ) : null}
    </nav>
  );
}
