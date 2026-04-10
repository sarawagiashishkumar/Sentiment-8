import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { AlertTriangle, ShoppingCart } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { triggerWarningAlarm } from "@/components/Shared/KiteLiveWarning";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const POLL_INTERVAL = 30000;

function isMarketHours() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}

export function BBEAlertMonitor({ authHeaders, alertSoundEnabled, playAlertSound }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastChecked, setLastChecked] = useState(null);
  const intervalRef = useRef(null);
  const alertedRef = useRef(new Set());

  const fetchAlerts = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const resp = await axios.get(`${API}/fno/bbe-alerts`, { headers: authHeaders, timeout: 15000 });
      const data = resp.data;
      setAlerts(data.alerts || []);
      setLastChecked(data.checked_at);

      // Trigger alert for new NOW BUY signals
      const nowBuys = (data.alerts || []).filter(a => a.now_buy);
      const newBuys = nowBuys.filter(a => !alertedRef.current.has(a.option_symbol));
      if (newBuys.length > 0 && alertSoundEnabled) {
        triggerWarningAlarm(
          "Budget Entry Zone Hit!",
          `${newBuys.map(a => a.option_symbol).join(", ")} — NOW BUY signal active`
        );
        if (playAlertSound) playAlertSound("target");
        newBuys.forEach(a => alertedRef.current.add(a.option_symbol));
      }
    } catch { /* silent */ }
    finally { if (!silent) setLoading(false); }
  }, [authHeaders, alertSoundEnabled, playAlertSound]);

  useEffect(() => {
    fetchAlerts();
    intervalRef.current = setInterval(() => {
      if (isMarketHours()) fetchAlerts(true);
    }, POLL_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchAlerts]);

  const nowBuyAlerts = alerts.filter(a => a.now_buy);
  const watchingAlerts = alerts.filter(a => !a.now_buy);

  if (alerts.length === 0 && !loading) return null;

  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="bbe-alert-monitor">
      <CardHeader className="py-3">
        <CardTitle className="flex items-center justify-between text-white text-sm">
          <span className="flex items-center gap-2">
            <ShoppingCart size={14} className="text-cyan-400" />
            Budget Entry Alerts
            {nowBuyAlerts.length > 0 && (
              <Badge className="bg-emerald-500/20 border-emerald-500/50 text-emerald-300 text-[10px] animate-pulse">
                {nowBuyAlerts.length} NOW BUY
              </Badge>
            )}
          </span>
          {lastChecked && (
            <span className="text-[10px] text-slate-500 font-normal">
              Checked: {new Date(lastChecked).toLocaleTimeString("en-IN")}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading && alerts.length === 0 ? (
          <p className="text-xs text-slate-400 animate-pulse">Scanning BBE zones...</p>
        ) : (
          <>
            {nowBuyAlerts.map((a) => (
              <div
                key={a.option_symbol}
                className="rounded-lg border border-emerald-500/50 bg-emerald-500/10 p-3 transition-all"
                data-testid={`bbe-now-buy-${a.option_symbol}`}
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <Badge className="bg-emerald-500 text-white text-[10px] font-bold px-2">NOW BUY</Badge>
                    <span className="font-mono text-sm text-emerald-200">{a.option_symbol}</span>
                    <span className="text-[10px] text-slate-400">{a.direction}</span>
                  </div>
                  <Badge className="border-cyan-500/50 bg-cyan-500/20 text-cyan-200 text-[10px]">
                    Score: {a.confluence_score}
                  </Badge>
                </div>
                <div className="mt-1.5 grid grid-cols-4 gap-2 text-[10px]">
                  <div>
                    <span className="text-slate-500">LTP</span>
                    <p className="font-mono text-emerald-300 font-bold">{a.live_ltp?.toFixed(2)}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">BBE</span>
                    <p className="font-mono text-cyan-300">{a.best_budget_entry?.toFixed(2)}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Entry</span>
                    <p className="font-mono text-slate-300">{a.entry_price?.toFixed(2)}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">SL</span>
                    <p className="font-mono text-rose-400">{a.stop_loss?.toFixed(2)}</p>
                  </div>
                </div>
              </div>
            ))}
            {watchingAlerts.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[10px] text-slate-500 font-semibold">Approaching BBE Zone</p>
                {watchingAlerts.slice(0, 6).map((a) => (
                  <div
                    key={a.option_symbol}
                    className="rounded-md border border-slate-700 bg-slate-900/70 p-2 text-[10px] flex items-center gap-3 flex-wrap"
                    data-testid={`bbe-watching-${a.option_symbol}`}
                  >
                    <span className="font-mono text-cyan-200">{a.option_symbol}</span>
                    <span className="text-slate-400">LTP: {a.live_ltp?.toFixed(2)}</span>
                    <span className="text-slate-400">BBE: {a.best_budget_entry?.toFixed(2)}</span>
                    <span className={`font-semibold ${a.pct_from_bbe <= 2 ? "text-amber-400" : "text-slate-500"}`}>
                      {a.pct_from_bbe > 0 ? "+" : ""}{a.pct_from_bbe}% from BBE
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
