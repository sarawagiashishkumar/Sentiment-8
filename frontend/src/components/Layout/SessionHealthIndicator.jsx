import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { AlertTriangle, Wifi, WifiOff } from "lucide-react";

const API = "/api";
const POLL_INTERVAL = 60000;

export function SessionHealthIndicator() {
  const [health, setHealth] = useState("checking");
  const intervalRef = useRef(null);

  const checkHealth = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/health`, { timeout: 15000 });
      const status = resp.data?.status;
      setHealth(status === "healthy" ? "online" : status === "degraded" ? "degraded" : "offline");
    } catch {
      setHealth("offline");
    }
  }, []);

  useEffect(() => {
    checkHealth();
    intervalRef.current = setInterval(checkHealth, POLL_INTERVAL);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [checkHealth]);

  const isOnline = health === "online";
  const isDegraded = health === "degraded";
  const isChecking = health === "checking";
  const label = isOnline ? "API Online" : isDegraded ? "Degraded" : isChecking ? "Checking..." : "Offline";
  const title = isOnline
    ? "Application API and database are healthy"
    : isDegraded
    ? "Application API is responding with a dependency issue"
    : isChecking
    ? "Checking application API health"
    : "Application API is unreachable — click to retry";

  return (
    <button
      type="button"
      onClick={checkHealth}
      className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all ${
        isOnline
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
          : isDegraded
          ? "border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
          : isChecking
          ? "border-slate-600 bg-slate-800/50 text-slate-400"
          : "border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
      }`}
      data-testid="session-health-indicator"
      aria-label={label}
      title={title}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          isOnline ? "bg-emerald-400 animate-pulse" : isDegraded ? "bg-amber-400" : isChecking ? "bg-slate-500" : "bg-rose-400"
        }`}
        data-testid="session-health-dot"
      />
      {isOnline ? (
        <>
          <Wifi size={12} />
          <span>{label}</span>
        </>
      ) : isDegraded ? (
        <>
          <AlertTriangle size={12} />
          <span>{label}</span>
        </>
      ) : isChecking ? (
        <span>{label}</span>
      ) : (
        <>
          <WifiOff size={12} />
          <span>{label}</span>
        </>
      )}
    </button>
  );
}
