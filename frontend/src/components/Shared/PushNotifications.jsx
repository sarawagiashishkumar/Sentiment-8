import { useState, useEffect, useCallback, useRef } from "react";
import { BellRing, BellOff } from "lucide-react";

const SW_PATH = "/sw-notifications.js";
const STORAGE_KEY = "push_notif_enabled";

/**
 * Hook to manage Service Worker push notifications.
 */
export function usePushNotifications() {
  const [enabled, setEnabled] = useState(() => sessionStorage.getItem(STORAGE_KEY) === "true");
  const [permission, setPermission] = useState(() =>
    typeof Notification !== "undefined" ? Notification.permission : "default"
  );
  const swRef = useRef(null);

  // Register Service Worker on mount
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register(SW_PATH).then((reg) => {
      swRef.current = reg;
    }).catch((err) => {
      console.error("SW registration failed:", err?.message);
    });
  }, []);

  const requestPermission = useCallback(async () => {
    if (typeof Notification === "undefined") return "denied";
    if (Notification.permission === "granted") {
      setPermission("granted");
      return "granted";
    }
    const result = await Notification.requestPermission();
    setPermission(result);
    return result;
  }, []);

  const toggle = useCallback(async () => {
    if (enabled) {
      setEnabled(false);
      sessionStorage.setItem(STORAGE_KEY, "false");
      return;
    }
    const perm = await requestPermission();
    if (perm === "granted") {
      setEnabled(true);
      sessionStorage.setItem(STORAGE_KEY, "true");
    }
  }, [enabled, requestPermission]);

  const sendPush = useCallback((title, body, tag = "alert") => {
    if (!enabled || permission !== "granted") return;
    if (swRef.current?.active) {
      swRef.current.active.postMessage({ type: "PUSH_NOTIFICATION", title, body, tag });
    } else if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      try {
        new Notification(title, { body, tag, icon: "/favicon.ico", requireInteraction: true });
      } catch (err) {
        console.error("Direct notification failed:", err?.message);
      }
    }
  }, [enabled, permission]);

  return { enabled, permission, toggle, sendPush };
}

/**
 * Toggle button for push notifications ON/OFF.
 */
export function PushNotifToggle({ enabled, permission, onToggle }) {
  const isBlocked = permission === "denied";

  return (
    <button
      onClick={onToggle}
      disabled={isBlocked}
      className={`relative rounded-lg p-1.5 transition-colors ${
        isBlocked
          ? "text-slate-600 cursor-not-allowed"
          : enabled
          ? "text-cyan-400 hover:text-cyan-300 hover:bg-slate-800"
          : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
      }`}
      data-testid="push-notif-toggle"
      title={
        isBlocked
          ? "Push notifications blocked by browser. Check site permissions."
          : enabled
          ? "Push notifications ON — click to disable"
          : "Push notifications OFF — click to enable"
      }
    >
      {enabled ? <BellRing size={15} /> : <BellOff size={15} />}
      {enabled && (
        <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
      )}
    </button>
  );
}
