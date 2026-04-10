import { useState, useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function KiteLiveWarning({ authHeaders }) {
  const [kiteStatus, setKiteStatus] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await axios.get(`${API}/kite/status`, { headers: authHeaders });
        setKiteStatus(r.data);
      } catch {
        setKiteStatus({ connected: false, reason: "api_error" });
      }
    };
    check();
  }, [authHeaders]);

  if (dismissed || !kiteStatus || kiteStatus.connected) return null;

  return (
    <div className="mb-4 flex items-start gap-3 rounded-lg border border-amber-600/50 bg-amber-950/40 p-3" data-testid="kite-live-warning">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-400" />
      <div className="flex-1">
        <p className="text-sm font-semibold text-amber-300">No Live Data Available</p>
        <p className="text-xs text-amber-400/80 mt-0.5">
          Kite Connect is not authenticated or the session has expired.
          All market data, heatmaps, F&O signals, and sector momentum require a live Kite connection.
          <strong className="text-amber-300"> Contact Admin</strong> to re-authenticate Kite in the Admin panel.
        </p>
        {kiteStatus.reason && (
          <p className="text-[10px] text-amber-500/70 mt-1 font-mono">Reason: {kiteStatus.reason}</p>
        )}
      </div>
      <button onClick={() => setDismissed(true)} className="shrink-0 text-amber-500 hover:text-amber-300" data-testid="kite-warning-dismiss">
        <X size={16} />
      </button>
    </div>
  );
}
