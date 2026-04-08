import { GaugeCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function AppFooter() {
  return (
    <footer className="mt-8" data-testid="footer-disclaimer">
      <Card className="border border-cyan-500/20 bg-slate-950/70">
        <CardContent className="pt-5">
          <p className="flex items-center gap-2 text-sm font-semibold text-cyan-300">
            <GaugeCircle size={14} /> Personal Testing & Educational Disclaimer
          </p>
          <p className="mt-2 text-xs leading-relaxed text-slate-300">
            This platform is an educational analytics system for personal testing. Signals, projections, and scorecards are model-based outputs
            and not trading advice. Market participation carries risk. Consult SEBI-registered advisors for investment decisions.
          </p>
        </CardContent>
      </Card>
    </footer>
  );
}
