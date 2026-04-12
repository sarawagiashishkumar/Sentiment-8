import { useState, useCallback, useEffect, useRef } from "react";
import { Bell, X, AlertTriangle, Info, CheckCircle, Trash2 } from "lucide-react";

const MAX_NOTIFICATIONS = 100;
const AUTO_CLEAR_HOURS = 24;

const CATEGORY_CONFIG = {
  critical: { icon: AlertTriangle, color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/30", badge: "bg-rose-500" },
  warning: { icon: AlertTriangle, color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/30", badge: "bg-amber-500" },
  success: { icon: CheckCircle, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30", badge: "bg-emerald-500" },
  info: { icon: Info, color: "text-cyan-400", bg: "bg-cyan-500/10 border-cyan-500/30", badge: "bg-cyan-500" },
};

export function useNotifications() {
  const [notifications, setNotifications] = useState([]);

  // Auto-clear old notifications
  useEffect(() => {
    const interval = setInterval(() => {
      const cutoff = Date.now() - AUTO_CLEAR_HOURS * 60 * 60 * 1000;
      setNotifications(prev => prev.filter(n => n.ts > cutoff));
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  const addNotification = useCallback((category, title, message, meta = {}) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setNotifications(prev => {
      const next = [{ id, category, title, message, ts: Date.now(), read: false, ...meta }, ...prev];
      return next.slice(0, MAX_NOTIFICATIONS);
    });
    return id;
  }, []);

  const markRead = useCallback((id) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }, []);

  const dismiss = useCallback((id) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  const unreadCount = notifications.filter(n => !n.read).length;

  return { notifications, unreadCount, addNotification, markRead, markAllRead, dismiss, clearAll };
}

export function NotificationBell({ unreadCount, onClick }) {
  return (
    <button
      onClick={onClick}
      className="relative rounded-lg p-1.5 text-slate-400 hover:text-cyan-300 hover:bg-slate-800 transition-colors"
      data-testid="notification-bell"
      aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
    >
      <Bell size={16} />
      {unreadCount > 0 && (
        <span
          className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white"
          data-testid="notification-badge"
        >
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </button>
  );
}

export function NotificationPanel({ notifications, isOpen, onClose, onMarkRead, onMarkAllRead, onDismiss, onClearAll }) {
  const panelRef = useRef(null);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return undefined;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target) && !e.target.closest('[data-testid="notification-bell"]')) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const grouped = {
    critical: notifications.filter(n => n.category === "critical"),
    warning: notifications.filter(n => n.category === "warning"),
    success: notifications.filter(n => n.category === "success"),
    info: notifications.filter(n => n.category === "info"),
  };

  const formatTime = (ts) => {
    const diff = Date.now() - ts;
    if (diff < 60000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return new Date(ts).toLocaleDateString();
  };

  return (
    <div
      ref={panelRef}
      className="fixed top-0 right-0 z-50 h-full w-80 sm:w-96 border-l border-slate-700 bg-slate-950/98 backdrop-blur-sm shadow-2xl transform transition-transform duration-200 animate-in slide-in-from-right"
      data-testid="notification-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Bell size={16} className="text-cyan-400" />
          <h3 className="text-sm font-semibold text-white">Notifications</h3>
          {notifications.length > 0 && (
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-400">
              {notifications.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {notifications.length > 0 && (
            <>
              <button
                onClick={onMarkAllRead}
                className="rounded p-1 text-[10px] text-slate-500 hover:text-cyan-400 transition-colors"
                data-testid="notification-mark-all-read"
                title="Mark all read"
              >
                <CheckCircle size={13} />
              </button>
              <button
                onClick={onClearAll}
                className="rounded p-1 text-[10px] text-slate-500 hover:text-rose-400 transition-colors"
                data-testid="notification-clear-all"
                title="Clear all"
              >
                <Trash2 size={13} />
              </button>
            </>
          )}
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            data-testid="notification-close"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Notifications list */}
      <div className="overflow-y-auto h-[calc(100%-52px)] px-3 py-2 space-y-1.5" data-testid="notification-list">
        {notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center" data-testid="notification-empty">
            <Bell size={28} className="text-slate-700 mb-2" />
            <p className="text-xs text-slate-500">No notifications yet</p>
            <p className="text-[10px] text-slate-600 mt-1">Alerts, warnings, and updates will appear here</p>
          </div>
        ) : (
          <>
            {["critical", "warning", "success", "info"].map(cat => {
              const items = grouped[cat];
              if (items.length === 0) return null;
              const cfg = CATEGORY_CONFIG[cat];
              const Icon = cfg.icon;
              return (
                <div key={cat} className="space-y-1" data-testid={`notification-group-${cat}`}>
                  <p className={`text-[10px] font-semibold uppercase tracking-wider ${cfg.color} px-1 pt-1`}>
                    {cat} ({items.length})
                  </p>
                  {items.map(n => (
                    <div
                      key={n.id}
                      className={`rounded-lg border p-2.5 transition-all cursor-pointer ${cfg.bg} ${!n.read ? "ring-1 ring-offset-0" : "opacity-70"}`}
                      style={{ ringColor: !n.read ? undefined : "transparent" }}
                      onClick={() => onMarkRead(n.id)}
                      data-testid={`notification-item-${n.id}`}
                    >
                      <div className="flex items-start gap-2">
                        <Icon size={13} className={`${cfg.color} mt-0.5 shrink-0`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <span className="text-xs font-semibold text-white truncate">{n.title}</span>
                            <div className="flex items-center gap-1 shrink-0">
                              <span className="text-[9px] text-slate-500 font-mono">{formatTime(n.ts)}</span>
                              {!n.read && <span className={`h-1.5 w-1.5 rounded-full ${cfg.badge}`} />}
                            </div>
                          </div>
                          <p className="text-[10px] text-slate-400 mt-0.5 leading-tight line-clamp-2">{n.message}</p>
                          {n.symbol && (
                            <span className="inline-block mt-1 rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-mono text-cyan-300">{n.symbol}</span>
                          )}
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); onDismiss(n.id); }}
                          className="text-slate-600 hover:text-slate-300 p-0.5 shrink-0"
                          data-testid={`notification-dismiss-${n.id}`}
                        >
                          <X size={10} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
