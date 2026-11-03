import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { AlertTriangle, Wifi, WifiOff } from "lucide-react";

const API = "/api";
const POLL_INTERVAL = 60000;
const REQUEST_TIMEOUT = 15000;
const RETRY_DELAY = 3000;
const FAILURES_BEFORE_OFFLINE = 2;

export function SessionHealthIndicator() {
  const [health, setHealth] = useState("checking");
  const intervalRef = useRef(null);
  const retryTimeoutRef = useRef(null);
  const requestInFlightRef = useRef(false);
  const consecutiveFailuresRef = useRef(0);

  const checkHealth = useCallback(async () => {
    if (requestInFlightRef.current) return;
    requestInFlightRef.current = true;

    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    try {
      const resp = await axios.get(`${API}/health`, { timeout: REQUEST_TIMEOUT });
      consecutiveFailuresRef.current = 0;
      setHealth(resp.data?.status === "healthy" ? "online" : "degraded");
    } catch {
      consecutiveFailuresRef.current += 1;
      setHealth(consecutiveFailuresRef.current >= FAILURES_BEFORE_OFFLINE ? "offline" : "degraded");

      if (consecutiveFailuresRef.current === 1) {
        retryTimeoutRef.current = window.setTimeout(() => {
          retryTimeoutRef.current = null;
          void checkHealth();
        }, RETRY_DELAY);
      }
    } finally {
      requestInFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    intervalRef.current = setInterval(() => void checkHealth(), POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
    };
  }, [checkHealth]);

  const isOnline = health === "online";
  const isDegraded = health === "degraded";
  const isChecking = health === "checking";
  const label = isOnline ? "API Online" : isDegraded ? "Degraded" : isChecking ? "Checking..." : "Offline";
  const title = isOnline
    ? "Application API and database are healthy"
    : isDegraded
    ? "The health check is delayed or a dependency is unavailable; retrying"
    : isChecking
    ? "Checking application API health"
    : "Application API is unreachable — click to retry";

  return (
    <button
      type="button"
      onClick={() => void checkHealth()}
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
      data-health-status={health}
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
