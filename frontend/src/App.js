import { useEffect, useRef, useState } from "react";
import axios from "axios";
import "@/App.css";

import { useAuth } from "@/hooks/useAuth";
import { LoginPage } from "@/components/Auth/LoginPage";
import { AppHeader } from "@/components/Layout/AppHeader";
import { AppSidebar } from "@/components/Layout/AppSidebar";
import { AppFooter } from "@/components/Layout/AppFooter";
import { HomeDashboard } from "@/components/Home/HomeDashboard";
import { KiteLiveWarning } from "@/components/Shared/KiteLiveWarning";
import { ErrorBoundary } from "@/components/Shared/ErrorBoundary";
import { useNotifications, NotificationBell, NotificationPanel } from "@/components/Shared/NotificationCenter";
import { usePushNotifications, PushNotifToggle } from "@/components/Shared/PushNotifications";
import { LiveHelpModule } from "@/components/Shared/LiveHelpModule";
import { UserCrmInbox } from "@/components/Shared/UserCrmInbox";
import { MultibaggerDashboard } from "@/components/Multibagger/MultibaggerDashboard";
import { FNODashboard } from "@/components/FNO/FNODashboard";
import { PortfolioDashboard } from "@/components/Portfolio/PortfolioDashboard";
import { AdminDashboard } from "@/components/Admin/AdminDashboard";
import { MarketHeatmapDashboard } from "@/components/MarketHeatmap/MarketHeatmapDashboard";
import { ReportsDashboard } from "@/components/Reports/ReportsDashboard";
import { WatchlistPanel } from "@/components/Watchlist/WatchlistPanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function App() {
  const {
    token, me, setMe, authHeaders, isAdmin, isOwner,
    loginUsername, setLoginUsername, loginLoading, loginError,
    onLogin, onLogout, hydrateMe, syncCredits,
  } = useAuth();

  const [currentPage, setCurrentPage] = useState("home");
  const [customPositions, setCustomPositions] = useState([]);
  const [alertSoundEnabled, setAlertSoundEnabled] = useState(false);
  const [notifPanelOpen, setNotifPanelOpen] = useState(false);

  const { notifications, unreadCount, addNotification, markRead, markAllRead, dismiss: dismissNotif, clearAll: clearAllNotifs, setNotifications } = useNotifications();
  const { enabled: pushEnabled, permission: pushPermission, toggle: togglePush, sendPush } = usePushNotifications();

  const audioContextRef = useRef(null);
  const urgentBuzzedRef = useRef(new Set());
  const targetBuzzedRef = useRef(new Set());
  const warningBuzzedRef = useRef(new Set());

  useEffect(() => { document.title = "AI Trading Dashboard"; }, []);

  // ── Load persisted notifications on login ─────────────────────────
  useEffect(() => {
    if (!token) return;
    axios.get(`${API}/notifications`, { headers: authHeaders }).then((res) => {
      const items = (res.data?.notifications || []).map((n) => ({
        id: `db-${n.ts}-${Math.random().toString(36).slice(2, 6)}`,
        category: n.category, title: n.title, message: n.message,
        ts: n.ts * 1000, read: n.read, symbol: n.symbol,
      }));
      if (items.length > 0) setNotifications(items);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ── Custom Positions Polling (adaptive: 5s market, 60s off-hours) ──
  const loadCustomPositions = async () => {
    if (!token) return;
    try {
      const response = await axios.get(`${API}/fno/custom-positions`, { headers: authHeaders });
      setCustomPositions(response.data || []);
      if (lastActivityRef.current) lastActivityRef.current = Date.now();
    } catch { /* keep silent during polling */ }
  };

  useEffect(() => {
    if (!token) return undefined;
    loadCustomPositions();

    const getPollingInterval = () => {
      const now = new Date();
      const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
      const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
      const isMarket = day > 0 && day < 6 && (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
      return isMarket ? 5000 : 60000;
    };

    let timer = null;
    const schedulePoll = () => {
      const interval = getPollingInterval();
      timer = setTimeout(() => {
        loadCustomPositions();
        schedulePoll();
      }, interval);
    };
    schedulePoll();
    return () => { if (timer) clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ── Keep-alive heartbeat with anti-sleep protocol ──────────────────
  const lastActivityRef = useRef(Date.now());
  const heartbeatTimerRef = useRef(null);
  const INACTIVITY_LIMIT_MS = 10 * 60 * 1000;
  const HEARTBEAT_INTERVAL_MS = 60000;

  useEffect(() => {
    if (!token) return undefined;

    const ping = () => {
      axios.get(`${API}/heartbeat`, { headers: authHeaders, timeout: 5000 }).catch(() => {});
    };

    const resetActivity = () => { lastActivityRef.current = Date.now(); };

    const interactionEvents = ["click", "scroll", "keydown", "mousemove", "touchstart", "focus"];
    interactionEvents.forEach(evt => window.addEventListener(evt, resetActivity, { passive: true }));

    const handleVisibility = () => { if (!document.hidden) resetActivity(); };
    document.addEventListener("visibilitychange", handleVisibility);

    const axiosInterceptor = axios.interceptors.response.use(
      (response) => { resetActivity(); return response; },
      (error) => { resetActivity(); return Promise.reject(error); },
    );

    ping();
    heartbeatTimerRef.current = setInterval(() => {
      const idleMs = Date.now() - lastActivityRef.current;
      if (idleMs < INACTIVITY_LIMIT_MS || !document.hidden) {
        ping();
      }
    }, HEARTBEAT_INTERVAL_MS);

    return () => {
      interactionEvents.forEach(evt => window.removeEventListener(evt, resetActivity));
      document.removeEventListener("visibilitychange", handleVisibility);
      axios.interceptors.response.eject(axiosInterceptor);
      if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
    };
  }, [token, authHeaders]);

  // ── Rich alert sound engine ──────────────────────────────────────
  const playAlertSound = (type = "urgent") => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioContextRef.current || audioContextRef.current.state === "closed") {
        audioContextRef.current = new AudioCtx();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === "suspended") ctx.resume();

      const scheduleBeep = (freq, startAt, duration, gainPeak = 0.55, waveType = "square") => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = waveType;
        osc.frequency.setValueAtTime(freq, startAt);
        gain.gain.setValueAtTime(0.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(gainPeak, startAt + 0.04);
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startAt);
        osc.stop(startAt + duration + 0.01);
      };

      const now = ctx.currentTime;
      if (type === "urgent") {
        scheduleBeep(1100, now, 0.28, 0.65, "square");
        scheduleBeep(900, now + 0.32, 0.28, 0.65, "square");
        scheduleBeep(1100, now + 0.64, 0.36, 0.70, "square");
      } else if (type === "target") {
        scheduleBeep(660, now, 0.30, 0.55, "sine");
        scheduleBeep(880, now + 0.35, 0.30, 0.55, "sine");
        scheduleBeep(1100, now + 0.70, 0.50, 0.60, "sine");
      } else if (type === "warning") {
        scheduleBeep(820, now, 0.35, 0.50, "triangle");
        scheduleBeep(820, now + 0.45, 0.35, 0.50, "triangle");
      }
    } catch { /* ignore autoplay restrictions */ }
  };

  // ── Comprehensive alert monitor ──────────────────────────────────
  useEffect(() => {
    if (!Array.isArray(customPositions) || customPositions.length === 0) return;
    if (typeof window === "undefined" || document.hidden) return;
    if (!alertSoundEnabled) return;

    const urgentAlertSet = new Set(["EXIT_URGENT_TIME", "EXIT_URGENT_LOSS", "RISKY_PREMIUM", "EXIT_NOW_HIGH_LOSS", "EXIT_URGENT_NO_RECOVERY"]);
    const warningAlertSet = new Set(["EXIT_PREMIUM_DECAY", "APPROACHING_SL", "LOSS_WARNING"]);
    const targetStateSet = new Set(["WATCHING_T1", "WATCHING_T2", "CLOSED_WIN"]);

    const freshUrgent = customPositions.filter((p) => urgentAlertSet.has(p.alert) && !urgentBuzzedRef.current.has(p.id));
    if (freshUrgent.length > 0) {
      playAlertSound("urgent");
      freshUrgent.forEach((p) => {
        urgentBuzzedRef.current.add(p.id);
        addNotification("critical", p.alert.replace(/_/g, " "), `${p.symbol || "Position"}: ${p.alert}`, { symbol: p.symbol });
        sendPush(`CRITICAL: ${p.alert.replace(/_/g, " ")}`, `${p.symbol || "Position"}: ${p.alert}`, "critical");
      });
    }

    const freshTargets = customPositions.filter((p) => targetStateSet.has(p.signal_state) && !targetBuzzedRef.current.has(`${p.id}_${p.signal_state}`));
    if (freshTargets.length > 0) {
      playAlertSound("target");
      freshTargets.forEach((p) => {
        targetBuzzedRef.current.add(`${p.id}_${p.signal_state}`);
        addNotification("success", p.signal_state.replace(/_/g, " "), `${p.symbol || "Position"}: ${p.signal_state}`, { symbol: p.symbol });
      });
    }

    const freshWarnings = customPositions.filter((p) => warningAlertSet.has(p.alert) && !warningBuzzedRef.current.has(p.id));
    if (freshWarnings.length > 0 && freshUrgent.length === 0) {
      playAlertSound("warning");
      freshWarnings.forEach((p) => {
        warningBuzzedRef.current.add(p.id);
        addNotification("warning", p.alert.replace(/_/g, " "), `${p.symbol || "Position"}: ${p.alert}`, { symbol: p.symbol });
        sendPush(`WARNING: ${p.alert.replace(/_/g, " ")}`, `${p.symbol || "Position"}: ${p.alert}`, "warning");
      });
    }

    // Persist new notifications to backend (debounced — only if we added any)
    if (freshUrgent.length > 0 || freshTargets.length > 0 || freshWarnings.length > 0) {
      const toSave = [
        ...freshUrgent.map(p => ({ category: "critical", title: p.alert.replace(/_/g, " "), message: `${p.symbol || "Position"}: ${p.alert}`, symbol: p.symbol })),
        ...freshTargets.map(p => ({ category: "success", title: p.signal_state.replace(/_/g, " "), message: `${p.symbol || "Position"}: ${p.signal_state}`, symbol: p.symbol })),
        ...freshWarnings.map(p => ({ category: "warning", title: p.alert.replace(/_/g, " "), message: `${p.symbol || "Position"}: ${p.alert}`, symbol: p.symbol })),
      ];
      axios.post(`${API}/notifications`, { notifications: toSave }, { headers: authHeaders }).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customPositions, alertSoundEnabled]);

  const enableAlertSound = async () => {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error("Audio not supported");
    if (!audioContextRef.current || audioContextRef.current.state === "closed") {
      audioContextRef.current = new AudioCtx();
    }
    const ctx = audioContextRef.current;
    if (ctx.state === "suspended") await ctx.resume();
    setAlertSoundEnabled(true);
  };

  const handleMarkAllRead = () => {
    markAllRead();
    axios.patch(`${API}/notifications/read-all`, {}, { headers: authHeaders }).catch(() => {});
  };

  const handleClearAll = () => {
    clearAllNotifs();
    axios.delete(`${API}/notifications`, { headers: authHeaders }).catch(() => {});
  };

  const handleLogout = async () => {
    await onLogout();
    setCurrentPage("home");
    setCustomPositions([]);
  };

  // ── Login gate ────────────────────────────────────────────────────
  if (!token || !me) {
    return (
      <LoginPage
        loginUsername={loginUsername} setLoginUsername={setLoginUsername}
        loginLoading={loginLoading} loginError={loginError} onLogin={onLogin}
      />
    );
  }

  // ── Main app shell ────────────────────────────────────────────────
  return (
    <main className="min-h-screen dashboard-dark-bg text-slate-100" data-testid="app-shell">
      <div className="dashboard-grid-overlay" />
      <div className="relative z-10 mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <AppHeader
          me={me} onLogout={handleLogout} authHeaders={authHeaders}
          notifBell={
            <>
              <PushNotifToggle enabled={pushEnabled} permission={pushPermission} onToggle={togglePush} />
              <NotificationBell unreadCount={unreadCount} onClick={() => setNotifPanelOpen(prev => !prev)} />
            </>
          }
        />
        <AppSidebar
          currentPage={currentPage} setCurrentPage={setCurrentPage}
          isAdmin={isAdmin}
          onAdminClick={() => {}}
        />

        {currentPage === "home" ? (
          <HomeDashboard setCurrentPage={setCurrentPage} />
        ) : null}

        {/* Market Data API Warning for all data-dependent sections */}
        {["multibagger", "fno", "portfolio", "heatmap", "reports", "watchlist"].includes(currentPage) && (
          <KiteLiveWarning authHeaders={authHeaders} addNotification={addNotification} />
        )}

        <ErrorBoundary>
        <UserCrmInbox authHeaders={authHeaders} />
        {currentPage === "multibagger" ? (
          <MultibaggerDashboard authHeaders={authHeaders} syncCredits={syncCredits} />
        ) : null}

        {currentPage === "fno" ? (
          <FNODashboard
            authHeaders={authHeaders} syncCredits={syncCredits} me={me} setMe={setMe}
            customPositions={customPositions} loadCustomPositions={loadCustomPositions}
            alertSoundEnabled={alertSoundEnabled} enableAlertSound={enableAlertSound}
            playAlertSound={playAlertSound}
          />
        ) : null}

        {currentPage === "portfolio" ? (
          <PortfolioDashboard authHeaders={authHeaders} syncCredits={syncCredits} />
        ) : null}

        {currentPage === "admin" && isAdmin ? (
          <AdminDashboard
            authHeaders={authHeaders} me={me}
            isAdmin={isAdmin} isOwner={isOwner}
            token={token} hydrateMe={hydrateMe}
          />
        ) : null}

        {currentPage === "heatmap" ? (
          <MarketHeatmapDashboard authHeaders={authHeaders} />
        ) : null}

        {currentPage === "reports" ? (
          <ReportsDashboard authHeaders={authHeaders} />
        ) : null}

        {currentPage === "watchlist" ? (
          <WatchlistPanel authHeaders={authHeaders} />
        ) : null}
        </ErrorBoundary>

        <AppFooter />

        <NotificationPanel
          notifications={notifications} isOpen={notifPanelOpen}
          onClose={() => setNotifPanelOpen(false)}
          onMarkRead={markRead} onMarkAllRead={handleMarkAllRead}
          onDismiss={dismissNotif} onClearAll={handleClearAll}
        />

        <LiveHelpModule authHeaders={authHeaders} me={me} />
      </div>
    </main>
  );
}
