import { useState, useEffect, useCallback, useRef } from "react";
import { AlertTriangle, X, Volume2 } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ALARM_URL = "https://cdn.pixabay.com/download/audio/2022/03/25/audio_25c0b2671e.mp3?filename=freesound_community-alarm-106447.mp3";

/**
 * Kite Session Health Monitor + "No Live Data" warning.
 * - Checks /api/kite/status every 60s
 * - Does NOT mention "Kite" by name — only "API"
 * - Non-sticky: only shows when API is down, auto-dismisses on reconnect
 * - Plays 5s loud alarm when connection drops
 */
export function KiteLiveWarning({ authHeaders }) {
  const [kiteStatus, setKiteStatus] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const prevConnected = useRef(null);
  const audioRef = useRef(null);
  const intervalRef = useRef(null);

  const playAlarm = useCallback(() => {
    try {
      if (!audioRef.current) {
        audioRef.current = new Audio(ALARM_URL);
      }
      audioRef.current.volume = 1.0;
      audioRef.current.currentTime = 0;
      audioRef.current.play().catch(() => {});
      // Stop after 5 seconds
      setTimeout(() => {
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current.currentTime = 0;
        }
      }, 5000);
    } catch {}
  }, []);

  const checkStatus = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/kite/status`, { headers: authHeaders, timeout: 10000 });
      const newStatus = r.data;
      setKiteStatus(newStatus);

      // If was connected and now disconnected → play alarm + show warning + browser notification
      if (prevConnected.current === true && !newStatus.connected) {
        setDismissed(false);
        playAlarm();
        // Browser notification
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("API Session Expired", {
            body: "Market data API authentication has expired. Please contact Admin to re-authenticate.",
            icon: "/favicon.ico",
          });
        }
      }
      // If reconnected, auto-dismiss warning
      if (newStatus.connected && !prevConnected.current) {
        setDismissed(true);
      }
      prevConnected.current = newStatus.connected;
    } catch {
      setKiteStatus({ connected: false, reason: "api_error" });
      if (prevConnected.current === true) {
        setDismissed(false);
        playAlarm();
      }
      prevConnected.current = false;
    }
  }, [authHeaders, playAlarm]);

  useEffect(() => {
    // Request notification permission
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
    checkStatus();
    intervalRef.current = setInterval(checkStatus, 60000); // Check every 60s
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    };
  }, [checkStatus]);

  if (dismissed || !kiteStatus || kiteStatus.connected) return null;

  return (
    <div className="mb-4 flex items-start gap-3 rounded-lg border border-amber-600/50 bg-amber-950/50 p-3 animate-pulse" data-testid="api-live-warning">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-400" />
      <div className="flex-1">
        <p className="text-sm font-semibold text-amber-300">No Live Data Available</p>
        <p className="text-xs text-amber-400/80 mt-0.5">
          Market data API authentication required. Live data, signals, and heatmaps are
          unavailable until the API session is re-authenticated.
          <strong className="text-amber-300"> Contact Admin.</strong>
        </p>
      </div>
      <div className="flex gap-1.5 shrink-0">
        <button onClick={playAlarm} className="text-amber-500 hover:text-amber-300 p-1" title="Test alarm" data-testid="api-warning-alarm">
          <Volume2 size={14} />
        </button>
        <button onClick={() => setDismissed(true)} className="text-amber-500 hover:text-amber-300 p-1" data-testid="api-warning-dismiss">
          <X size={16} />
        </button>
      </div>
    </div>
  );
}

/**
 * Popup notification for when a data fetch fails.
 * Shows modal overlay with alarm sound.
 */
export function DataFetchErrorPopup({ show, onClose }) {
  const audioRef = useRef(null);

  useEffect(() => {
    if (show) {
      try {
        audioRef.current = new Audio(ALARM_URL);
        audioRef.current.volume = 1.0;
        audioRef.current.play().catch(() => {});
        setTimeout(() => {
          if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; }
        }, 5000);
      } catch {}
    }
    return () => {
      if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    };
  }, [show]);

  if (!show) return null;

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="data-fetch-error-popup">
      <div className="w-full max-w-md rounded-xl border-2 border-red-600 bg-slate-950 p-6 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle size={28} className="text-red-400" />
          <h3 className="text-lg font-bold text-red-300">No Live Data Fetched</h3>
        </div>
        <p className="text-sm text-slate-300 mb-2">
          <strong className="text-red-400">Error:</strong> API Authentication Failed.
        </p>
        <p className="text-xs text-slate-400 mb-6">
          The market data API session has expired or is not connected. No live results can be generated.
          Please contact Admin to re-authenticate the API connection.
        </p>
        <button
          onClick={onClose}
          className="w-full rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-500 transition-colors"
          data-testid="data-fetch-error-close"
        >
          Understood
        </button>
      </div>
    </div>
  );
}
