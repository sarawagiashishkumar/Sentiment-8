import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Check, X, Zap, Star, Crown, Infinity } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TIER_ICONS = { free: Zap, basic: Star, pro: Crown, unlimited: Infinity };
const TIER_COLORS = {
  free: "border-slate-600 bg-slate-900/60",
  basic: "border-cyan-600/50 bg-cyan-950/30",
  pro: "border-amber-500/50 bg-amber-950/30",
  unlimited: "border-violet-500/50 bg-violet-950/30 ring-1 ring-violet-500/20",
};
const TIER_ACCENT = { free: "text-slate-400", basic: "text-cyan-400", pro: "text-amber-400", unlimited: "text-violet-400" };

const FEATURE_LABELS = {
  fno_generate: "F&O Signal Generation",
  multibagger_generate: "Multibagger Screener",
  portfolio_analyze: "Portfolio Analysis",
  custom_position: "Custom Position Tracking",
  backtest_run: "Strategy Backtester",
  iv_collect: "IV Data Collection",
  reports_view: "Reports Access",
  watchlist_add: "Watchlist Management",
  alert_rule_create: "Alert Rule Creation",
};

const LIMIT_LABELS = {
  fno_generate_daily: "F&O Generations / Day",
  multibagger_generate_daily: "Multibagger Scans / Day",
  portfolio_analyze_daily: "Portfolio Analyses / Day",
  custom_position_total: "Max Custom Positions",
  backtest_run_daily: "Backtests / Day",
  alert_rules_total: "Max Alert Rules",
  watchlist_items_total: "Max Watchlist Items",
};

function formatLimit(val) {
  if (val === 999999 || val >= 999999) return "Unlimited";
  return String(val);
}

export function PlanComparisonPage({ authHeaders, me, currentPlan }) {
  const [packages, setPackages] = useState({});
  const [costs, setCosts] = useState({});

  const fetchPackages = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/packages`, { headers: authHeaders });
      setPackages(res.data.packages || {});
      setCosts(res.data.default_feature_costs || {});
    } catch (err) { console.error(err); }
  }, [authHeaders]);

  useEffect(() => { fetchPackages(); }, [fetchPackages]);

  const tierOrder = ["free", "basic", "pro", "unlimited", ...Object.keys(packages).filter(k => !["free", "basic", "pro", "unlimited"].includes(k))];
  const orderedTiers = tierOrder.filter(k => packages[k]);

  return (
    <section className="space-y-6" data-testid="plan-comparison-page">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-bold text-white">Choose Your Plan</h1>
        <p className="text-sm text-slate-400">Compare features and limits across tiers. {me?.package && <span>You are on <span className="text-cyan-400 font-semibold">{packages[me.package]?.label || me.package}</span>.</span>}</p>
      </div>

      {/* Tier Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="plan-grid">
        {orderedTiers.map((key) => {
          const pkg = packages[key];
          const Icon = TIER_ICONS[key] || Star;
          const isActive = (currentPlan || me?.package || "free") === key;
          return (
            <Card key={key} className={`relative transition-all ${TIER_COLORS[key] || "border-slate-600 bg-slate-900/60"} ${isActive ? "ring-2 ring-cyan-400" : ""}`} data-testid={`plan-card-${key}`}>
              {isActive && <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-cyan-500 text-slate-900 text-[9px] font-bold px-2 py-0.5 rounded-full">CURRENT</div>}
              <CardContent className="pt-5 pb-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Icon size={18} className={TIER_ACCENT[key] || "text-slate-400"} />
                  <span className="text-lg font-bold text-white">{pkg.label}</span>
                </div>
                <div className="text-2xl font-bold text-white">
                  {pkg.credits >= 999999 ? <Infinity size={28} className="inline text-violet-400" /> : <>{pkg.credits} <span className="text-sm font-normal text-slate-400">credits</span></>}
                </div>

                {/* Limits */}
                <div className="space-y-1.5 pt-2 border-t border-slate-700/50">
                  {Object.entries(LIMIT_LABELS).map(([lk, label]) => {
                    const val = pkg.limits?.[lk] ?? 0;
                    return (
                      <div key={lk} className="flex items-center justify-between text-[10px]">
                        <span className="text-slate-400">{label}</span>
                        <span className={`font-mono font-semibold ${val >= 999999 ? "text-emerald-400" : val > 0 ? "text-slate-200" : "text-slate-600"}`}>
                          {formatLimit(val)}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Feature Access */}
                <div className="space-y-1 pt-2 border-t border-slate-700/50">
                  <p className="text-[9px] text-slate-500 font-semibold">Feature Access</p>
                  {Object.entries(FEATURE_LABELS).map(([fk, label]) => {
                    const cost = costs[fk] ?? 0;
                    const hasAccess = cost === 0 || pkg.credits >= cost;
                    return (
                      <div key={fk} className="flex items-center gap-1.5 text-[10px]">
                        {hasAccess ? <Check size={10} className="text-emerald-400 shrink-0" /> : <X size={10} className="text-slate-600 shrink-0" />}
                        <span className={hasAccess ? "text-slate-300" : "text-slate-600"}>{label}</span>
                        {cost > 0 && <span className="ml-auto text-slate-500 font-mono">{cost} cr</span>}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="text-center text-[10px] text-slate-600">Contact admin to upgrade your plan or add credits.</p>
    </section>
  );
}

/** Modal that appears when credits drop below threshold */
export function LowCreditsModal({ me, authHeaders, isOpen, onClose }) {
  const [packages, setPackages] = useState({});

  useEffect(() => {
    if (!isOpen) return;
    axios.get(`${API}/admin/packages`, { headers: authHeaders }).then(r => setPackages(r.data.packages || {})).catch(() => {});
  }, [isOpen, authHeaders]);

  if (!isOpen) return null;

  const currentPkg = packages[me?.package || "free"];
  const upgrades = Object.entries(packages).filter(([k]) => {
    const cur = packages[me?.package || "free"];
    return cur && packages[k].credits > cur.credits;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose} data-testid="low-credits-modal">
      <div className="bg-slate-950 rounded-xl border border-amber-500/40 p-5 max-w-md w-full mx-4 space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-amber-300">Credits Running Low</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={16} /></button>
        </div>
        <p className="text-xs text-slate-400">
          You have <span className="text-amber-300 font-bold">{Math.round(me?.credits || 0)}</span> credits remaining on <span className="text-white font-semibold">{currentPkg?.label || "Free"}</span>.
        </p>
        {upgrades.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] text-slate-500 font-semibold">Upgrade options:</p>
            {upgrades.map(([key, pkg]) => (
              <div key={key} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2">
                <div>
                  <span className="text-xs font-bold text-white">{pkg.label}</span>
                  <span className="ml-2 text-[10px] text-cyan-400">{pkg.credits >= 999999 ? "Unlimited" : pkg.credits} credits</span>
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="text-[10px] text-slate-500">Contact admin to upgrade or request a top-up.</p>
        <Button onClick={onClose} className="w-full h-8 bg-amber-600 text-white hover:bg-amber-500 text-xs" data-testid="low-credits-dismiss">Got It</Button>
      </div>
    </div>
  );
}
