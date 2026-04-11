import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { AlertTriangle, X, Volume2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ALARM_URL = "https://cdn.pixabay.com/download/audio/2022/03/25/audio_25c0b2671e.mp3";
const POLL_INTERVAL_MS = 60000; // 60 seconds
const ALARM_DURATION_MS = 5000; // 5 seconds loud alarm

/**
 * Play the alarm sound at MAXIMUM volume for exactly 5 seconds.
 * Used for critical warnings only (API disconnection, network errors).
 * NOT used for success events (target achievements).
 */
function playAlarmSound() {
  try {
    const audio = new Audio(ALARM_URL);
    audio.volume = 1.0; // Maximum volume
    audio.loop = true;   // Loop during the 5-second window
    audio.play().catch(() => {});
    // Stop after 5 seconds
    setTimeout(() => {
      audio.loop = false;
      audio.pause();
      audio.currentTime = 0;
    }, ALARM_DURATION_MS);
  } catch (audioErr) {
    console.debug("Audio blocked by browser policy:", audioErr.message);
  }
}

/**
 * Request browser notification permission (called once on mount).
 */
function requestNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }
}

/**
 * Show a browser notification for critical warnings.
 */
function showBrowserNotification(title, body) {
  if ("Notification" in window && Notification.permission === "granted") {
    try {
      new Notification(title, { body, icon: "/favicon.ico" });
    } catch (err) { console.debug("Browser notification error:", err.message); }
  }
}


// ── Main Component: Background API Health Polling ────────────────────────────

export function KiteLiveWarning({ authHeaders }) {
  const [disconnected, setDisconnected] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [lastDisconnectTime, setLastDisconnectTime] = useState(null);
  const intervalRef = useRef(null);
  const alarmPlayedRef = useRef(false);
  const disconnectedRef = useRef(false);

  const checkHealth = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/kite/status`, {
        headers: authHeaders,
        timeout: 8000,
      });
      const isConnected = resp.data?.connected === true;

      if (!isConnected) {
        // Newly disconnected — trigger alarm
        if (!disconnectedRef.current && !alarmPlayedRef.current) {
          playAlarmSound();
          showBrowserNotification(
            "API Authentication Failed",
            "Market data connection lost. Please re-authenticate immediately."
          );
          alarmPlayedRef.current = true;
          setLastDisconnectTime(new Date());
        }
        disconnectedRef.current = true;
        setDisconnected(true);
        setDismissed(false); // re-show on each detection
      } else {
        // Reconnected — reset state
        disconnectedRef.current = false;
        setDisconnected(false);
        alarmPlayedRef.current = false;
      }
    } catch (netErr) {
      console.error("KiteLiveWarning: health check network error:", netErr.message);
      // Network error to our own backend — also a disconnect
      if (!disconnectedRef.current && !alarmPlayedRef.current) {
        playAlarmSound();
        showBrowserNotification(
          "Network Connection Lost",
          "Unable to reach the server. Check your internet connection."
        );
        alarmPlayedRef.current = true;
        setLastDisconnectTime(new Date());
      }
      disconnectedRef.current = true;
      setDisconnected(true);
      setDismissed(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    requestNotificationPermission();
    checkHealth(); // immediate check
    intervalRef.current = setInterval(checkHealth, POLL_INTERVAL_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [checkHealth]);

  // Don't render if not disconnected or user dismissed it
  if (!disconnected || dismissed) return null;

  return (
    <div
      className="mb-4 rounded-lg border border-rose-500/60 bg-rose-950/80 p-4 shadow-lg shadow-rose-500/10"
      data-testid="api-disconnect-warning"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-full bg-rose-500/20 p-2">
          <AlertTriangle size={18} className="text-rose-400" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-rose-200 text-sm flex items-center gap-2">
            <Volume2 size={14} className="text-rose-400 animate-pulse" />
            API Authentication Failed
          </h3>
          <p className="text-xs text-rose-300/80 mt-1">
            Live market data feed is disconnected. Your signals and heatmaps may show stale data.
            Please re-authenticate from the <strong>Admin panel</strong> immediately.
          </p>
          {lastDisconnectTime && (
            <p className="text-[10px] text-rose-400/60 mt-1 font-mono">
              Detected: {lastDisconnectTime.toLocaleTimeString("en-IN")}
            </p>
          )}
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-rose-400 hover:text-rose-200 p-1 transition-colors"
          data-testid="dismiss-warning"
          title="Dismiss (will re-appear if still disconnected)"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}


// ── Exportable alarm function for use in other components ─────────────────────

/**
 * Call this from any component that needs to trigger the warning alarm.
 * Only for WARNING events (not success events like target achievements).
 */
export function triggerWarningAlarm(title, message) {
  playAlarmSound();
  showBrowserNotification(title || "Warning", message || "An issue requires your attention.");
}


// ── DataFetchErrorPopup: Centered popup for heatmaps etc ─────────────────────

function isMarketCurrentlyClosed() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return true;
  const totalMins = h * 60 + m;
  return totalMins < 555 || totalMins > 930;
}

export function DataFetchErrorPopup({ show, onClose }) {
  const [marketClosed, setMarketClosed] = useState(false);

  useEffect(() => {
    if (show) {
      playAlarmSound();
      setMarketClosed(isMarketCurrentlyClosed());
      showBrowserNotification("Data Fetch Failed", "Unable to load live market data.");
    }
  }, [show]);

  if (!show) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="data-fetch-error-overlay">
      <div
        className="relative mx-4 w-full max-w-md rounded-xl border border-amber-500/60 bg-slate-950 p-6 shadow-2xl shadow-amber-500/10"
        data-testid="data-fetch-error-popup"
        role="alert"
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="rounded-full bg-amber-500/20 p-3">
            <AlertTriangle size={28} className="text-amber-400" />
          </div>
          <h3 className="text-lg font-bold text-amber-200">Data Fetch Failed</h3>
          {marketClosed ? (
            <p className="text-sm text-amber-300/80">
              <strong>Market is currently closed.</strong> Live data will not be available until the next trading session (Mon-Fri, 9:15 AM - 3:30 PM IST). Cached data may be shown instead.
            </p>
          ) : (
            <p className="text-sm text-amber-300/80">
              Unable to fetch live market data. Check Market Data API authentication in the Admin panel.
            </p>
          )}
          <button
            onClick={onClose}
            className="mt-2 rounded-lg bg-amber-600 px-6 py-2 text-sm font-semibold text-white hover:bg-amber-500 transition-colors"
            data-testid="dismiss-fetch-error"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
