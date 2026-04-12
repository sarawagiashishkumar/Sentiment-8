import { useState, useEffect, useRef } from "react";
import { RefreshCw } from "lucide-react";

/**
 * Auto-refresh countdown indicator.
 * Shows a circular progress ring + seconds remaining until next refresh.
 * Renders inline (compact) for use in heatmap headers.
 */
export function RefreshCountdown({ intervalMs = 30000, isActive = true, onManualRefresh }) {
  const [secondsLeft, setSecondsLeft] = useState(Math.floor(intervalMs / 1000));
  const startRef = useRef(Date.now());

  useEffect(() => {
    if (!isActive) return undefined;
    startRef.current = Date.now();
    setSecondsLeft(Math.floor(intervalMs / 1000));

    const tick = setInterval(() => {
      const elapsed = Date.now() - startRef.current;
      const remaining = Math.max(0, Math.ceil((intervalMs - elapsed) / 1000));
      setSecondsLeft(remaining);
      if (remaining <= 0) {
        startRef.current = Date.now();
        setSecondsLeft(Math.floor(intervalMs / 1000));
      }
    }, 1000);
    return () => clearInterval(tick);
  }, [intervalMs, isActive]);

  const totalSecs = Math.floor(intervalMs / 1000);
  const progress = isActive ? ((totalSecs - secondsLeft) / totalSecs) * 100 : 0;
  const radius = 8;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  return (
    <div className="flex items-center gap-1.5" data-testid="refresh-countdown">
      {/* Circular progress ring */}
      <div className="relative" style={{ width: 22, height: 22 }}>
        <svg width="22" height="22" className="transform -rotate-90">
          <circle cx="11" cy="11" r={radius} fill="none" stroke="rgba(100,116,139,0.3)" strokeWidth="2" />
          <circle
            cx="11" cy="11" r={radius} fill="none"
            stroke={isActive ? "rgb(6, 182, 212)" : "rgba(100,116,139,0.5)"}
            strokeWidth="2"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="transition-all duration-1000 ease-linear"
          />
        </svg>
      </div>
      <span className="text-[10px] font-mono text-slate-500 tabular-nums w-5 text-center" data-testid="refresh-seconds">
        {isActive ? `${secondsLeft}s` : "--"}
      </span>
      {onManualRefresh && (
        <button
          onClick={onManualRefresh}
          className="text-slate-500 hover:text-cyan-400 transition-colors p-0.5"
          title="Refresh now"
          data-testid="refresh-manual-btn"
        >
          <RefreshCw size={11} />
        </button>
      )}
    </div>
  );
}
