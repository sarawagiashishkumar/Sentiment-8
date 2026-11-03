import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { Wifi, WifiOff } from "lucide-react";

const API = "/api";
const POLL_INTERVAL = 60000;

export function SessionHealthIndicator({ authHeaders }) {
  const [connected, setConnected] = useState(null);
  const intervalRef = useRef(null);

  const checkHealth = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/kite/status`, {
        headers: authHeaders,
        timeout: 8000,
      });
      setConnected(resp.data?.connected === true);
    } catch {
      setConnected(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    checkHealth();
    intervalRef.current = setInterval(checkHealth, POLL_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [checkHealth]);

  const isLive = connected === true;
  const isLoading = connected === null;

  return (
    <button
      type="button"
      onClick={checkHealth}
      className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all ${
        isLive
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
          : isLoading
          ? "border-slate-600 bg-slate-800/50 text-slate-400"
          : "border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
      }`}
      data-testid="session-health-indicator"
      title={isLive ? "API Connected — Live data active" : "API Disconnected — Click to retry"}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          isLive ? "bg-emerald-400 animate-pulse" : isLoading ? "bg-slate-500" : "bg-rose-400"
        }`}
        data-testid="session-health-dot"
      />
      {isLive ? (
        <>
          <Wifi size={12} />
          <span>Live</span>
        </>
      ) : isLoading ? (
        <span>Checking...</span>
      ) : (
        <>
          <WifiOff size={12} />
          <span>Offline</span>
        </>
      )}
    </button>
  );
}
