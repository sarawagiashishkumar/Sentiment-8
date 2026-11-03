import { useEffect, useRef, useState } from "react";
import axios from "axios";
import "App.css";

import { useAuth } from "hooks/useAuth";
import { useAlertEngine } from "hooks/useAlertEngine";
import { LoginPage } from "components/Auth/LoginPage";
import { AppHeader } from "components/Layout/AppHeader";
import { AppSidebar } from "components/Layout/AppSidebar";
import { AppFooter } from "components/Layout/AppFooter";
import { HomeDashboard } from "components/Home/HomeDashboard";
import { KiteLiveWarning } from "components/Shared/KiteLiveWarning";
import { ErrorBoundary } from "components/Shared/ErrorBoundary";
import { useNotifications, NotificationBell, NotificationPanel } from "components/Shared/NotificationCenter";
import { usePushNotifications, PushNotifToggle } from "components/Shared/PushNotifications";
import { LiveHelpModule } from "components/Shared/LiveHelpModule";
import { UserCrmInbox } from "components/Shared/UserCrmInbox";
import { MultibaggerDashboard } from "components/Multibagger/MultibaggerDashboard";
import { FNODashboard } from "components/FNO/FNODashboard";
import { PortfolioDashboard } from "components/Portfolio/PortfolioDashboard";
import { AdminDashboard } from "components/Admin/AdminDashboard";
import { MarketHeatmapDashboard } from "components/MarketHeatmap/MarketHeatmapDashboard";
import { ReportsDashboard } from "components/Reports/ReportsDashboard";
import { WatchlistPanel } from "components/Watchlist/WatchlistPanel";
import { PlanComparisonPage, LowCreditsModal } from "components/Shared/PlanComparison";
import { NewsSentimentPanel } from "components/News/NewsSentimentPanel";

const API = "/api";

export default function App() {
  const {
    token, me, setMe, authHeaders, isAdmin, isOwner,
    loginUsername, setLoginUsername, loginLoading, loginError,
    onLogin, onLogout, hydrateMe, syncCredits,
  } = useAuth();

  const [currentPage, setCurrentPage] = useState("home");
  const handlePageChange = (page) => { setCurrentPage(page); lastActivityRef.current = Date.now(); };
  const [customPositions, setCustomPositions] = useState([]);
  const [alertSoundEnabled, setAlertSoundEnabled] = useState(false);
  const [notifPanelOpen, setNotifPanelOpen] = useState(false);
  const [lowCreditsOpen, setLowCreditsOpen] = useState(false);
  const lowCreditsShownRef = useRef(false);

  const { notifications, unreadCount, addNotification, markRead, markAllRead, dismiss: dismissNotif, clearAll: clearAllNotifs, setNotifications } = useNotifications();
  const { enabled: pushEnabled, permission: pushPermission, toggle: togglePush, sendPush } = usePushNotifications();

  const { playAlertSound, enableAlertSound } = useAlertEngine({
    customPositions, alertSoundEnabled, authHeaders, addNotification, sendPush,
  });

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
    } catch { /* keep silent during polling */ }
  };

  useEffect(() => {
    if (!token) return undefined;
    loadCustomPositions();

    const getInterval = () => {
      const now = new Date();
      const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
      const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
      return day > 0 && day < 6 && (h * 60 + m) >= 555 && (h * 60 + m) <= 930 ? 5000 : 60000;
    };

    let timer = null;
    const poll = () => { timer = setTimeout(() => { loadCustomPositions(); poll(); }, getInterval()); };
    poll();
    return () => { if (timer) clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleMarkAllRead = () => { markAllRead(); axios.patch(`${API}/notifications/read-all`, {}, { headers: authHeaders }).catch(() => {}); };
  const handleClearAll = () => { clearAllNotifs(); axios.delete(`${API}/notifications`, { headers: authHeaders }).catch(() => {}); };
  const handleLogout = async () => { await onLogout(); handlePageChange("home"); setCustomPositions([]); };

  // ── Low credits modal trigger (once per session when credits < 5) ──
  useEffect(() => {
    if (!me || me.role === "owner" || lowCreditsShownRef.current) return;
    const credits = Number(me.credits || 0);
    if (credits > 0 && credits < 5) {
      setLowCreditsOpen(true);
      lowCreditsShownRef.current = true;
    }
  }, [me]);

  // ── Login gate ────────────────────────────────────────────────────
  if (!token || !me) {
    return <LoginPage loginUsername={loginUsername} setLoginUsername={setLoginUsername} loginLoading={loginLoading} loginError={loginError} onLogin={onLogin} />;
  }

  return (
    <main className="min-h-screen dashboard-dark-bg text-slate-100 overflow-x-hidden" data-testid="app-shell">
      <div className="dashboard-grid-overlay" />
      <div className="relative z-10 mx-auto w-full max-w-7xl px-3 py-4 sm:px-6 lg:px-8 overflow-x-hidden">
        <AppHeader me={me} onLogout={handleLogout} authHeaders={authHeaders}
          notifBell={<><PushNotifToggle enabled={pushEnabled} permission={pushPermission} onToggle={togglePush} /><NotificationBell unreadCount={unreadCount} onClick={() => setNotifPanelOpen(p => !p)} /></>}
        />
        <AppSidebar currentPage={currentPage} setCurrentPage={handlePageChange} isAdmin={isAdmin} onAdminClick={() => {}} />

        {currentPage === "home" && <>
          <HomeDashboard setCurrentPage={handlePageChange} />
          <NewsSentimentPanel authHeaders={authHeaders} />
        </>}
        {["multibagger", "fno", "portfolio", "heatmap", "reports", "watchlist"].includes(currentPage) && <KiteLiveWarning authHeaders={authHeaders} addNotification={addNotification} />}

        <ErrorBoundary>
          <UserCrmInbox authHeaders={authHeaders} />
          {currentPage === "multibagger" && <MultibaggerDashboard authHeaders={authHeaders} syncCredits={syncCredits} />}
          {currentPage === "fno" && <FNODashboard authHeaders={authHeaders} syncCredits={syncCredits} me={me} setMe={setMe} customPositions={customPositions} loadCustomPositions={loadCustomPositions} alertSoundEnabled={alertSoundEnabled} enableAlertSound={() => { enableAlertSound(); setAlertSoundEnabled(true); }} playAlertSound={playAlertSound} />}
          {currentPage === "portfolio" && <PortfolioDashboard authHeaders={authHeaders} syncCredits={syncCredits} />}
          {currentPage === "admin" && isAdmin && <AdminDashboard authHeaders={authHeaders} me={me} isAdmin={isAdmin} isOwner={isOwner} token={token} hydrateMe={hydrateMe} />}
          {currentPage === "heatmap" && <MarketHeatmapDashboard authHeaders={authHeaders} />}
          {currentPage === "reports" && <ReportsDashboard authHeaders={authHeaders} />}
          {currentPage === "watchlist" && <WatchlistPanel authHeaders={authHeaders} />}
          {currentPage === "plans" && <PlanComparisonPage authHeaders={authHeaders} me={me} />}
        </ErrorBoundary>

        <AppFooter />
        <NotificationPanel notifications={notifications} isOpen={notifPanelOpen} onClose={() => setNotifPanelOpen(false)} onMarkRead={markRead} onMarkAllRead={handleMarkAllRead} onDismiss={dismissNotif} onClearAll={handleClearAll} />
        <LiveHelpModule authHeaders={authHeaders} me={me} />
        <LowCreditsModal me={me} authHeaders={authHeaders} isOpen={lowCreditsOpen} onClose={() => setLowCreditsOpen(false)} />
      </div>
    </main>
  );
}
