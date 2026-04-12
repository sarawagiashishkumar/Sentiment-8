import { useEffect, useRef, useState } from "react";
import axios from "axios";
import "@/App.css";

import { useAuth } from "@/hooks/useAuth";
import { LoginPage } from "@/components/Auth/LoginPage";
import { AppHeader } from "@/components/Layout/AppHeader";
import { AppSidebar } from "@/components/Layout/AppSidebar";
import { AppFooter } from "@/components/Layout/AppFooter";
import { HomeDashboard } from "@/components/Home/HomeDashboard";
import { MultibaggerDashboard } from "@/components/Multibagger/MultibaggerDashboard";
import { FNODashboard } from "@/components/FNO/FNODashboard";
import { PortfolioDashboard } from "@/components/Portfolio/PortfolioDashboard";
import { AdminDashboard } from "@/components/Admin/AdminDashboard";
import { MarketHeatmapDashboard } from "@/components/MarketHeatmap/MarketHeatmapDashboard";
import { KiteLiveWarning } from "@/components/Shared/KiteLiveWarning";
import { ErrorBoundary } from "@/components/Shared/ErrorBoundary";

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

  const audioContextRef = useRef(null);
  const urgentBuzzedRef = useRef(new Set());
  const targetBuzzedRef = useRef(new Set());
  const warningBuzzedRef = useRef(new Set());

  useEffect(() => { document.title = "AI Trading Dashboard"; }, []);

  // ── Custom Positions Polling ──────────────────────────────────────
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
    const timer = setInterval(() => { loadCustomPositions(); }, 5000);
    return () => clearInterval(timer);
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
      freshUrgent.forEach((p) => urgentBuzzedRef.current.add(p.id));
    }

    const freshTargets = customPositions.filter((p) => targetStateSet.has(p.signal_state) && !targetBuzzedRef.current.has(`${p.id}_${p.signal_state}`));
    if (freshTargets.length > 0) {
      playAlertSound("target");
      freshTargets.forEach((p) => targetBuzzedRef.current.add(`${p.id}_${p.signal_state}`));
    }

    const freshWarnings = customPositions.filter((p) => warningAlertSet.has(p.alert) && !warningBuzzedRef.current.has(p.id));
    if (freshWarnings.length > 0 && freshUrgent.length === 0) {
      playAlertSound("warning");
      freshWarnings.forEach((p) => warningBuzzedRef.current.add(p.id));
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
        <AppHeader me={me} onLogout={handleLogout} authHeaders={authHeaders} />
        <AppSidebar
          currentPage={currentPage} setCurrentPage={setCurrentPage}
          isAdmin={isAdmin}
          onAdminClick={() => {}}
        />

        {currentPage === "home" ? (
          <HomeDashboard setCurrentPage={setCurrentPage} />
        ) : null}

        {/* Market Data API Warning for all data-dependent sections */}
        {["multibagger", "fno", "portfolio", "heatmap"].includes(currentPage) && (
          <KiteLiveWarning authHeaders={authHeaders} />
        )}

        <ErrorBoundary>
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
        </ErrorBoundary>

        <AppFooter />
      </div>
    </main>
  );
}
