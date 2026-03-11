import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  FileUp,
  GaugeCircle,
  Home,
  KeyRound,
  LogOut,
  Minus,
  Plus,
  RefreshCw,
  Shield,
  Sparkles,
  TrendingUp,
  UserCog,
  X,
} from "lucide-react";
import "@/App.css";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
};

const formatTime = (iso) => {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

const formatExpiryDate = (isoDate) => {
  if (!isoDate) return "-";
  const match = String(isoDate).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  return `${day}-${month}-${year}`;
};

const formatSignedInr = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : numeric < 0 ? "-" : "";
  return `${sign}₹${Math.abs(numeric).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
};

const directionBadge = (direction) => {
  if (direction === "BULLISH") return "bg-emerald-600 text-white border-emerald-700";
  if (direction === "BEARISH") return "bg-rose-600 text-white border-rose-700";
  return "bg-slate-300 text-slate-800 border-slate-400";
};

const qualityBadge = (quality) => {
  if (quality === "HIGH") return "bg-emerald-600 text-white border-emerald-700";
  if (quality === "MEDIUM") return "bg-amber-500 text-white border-amber-600";
  return "bg-slate-300 text-slate-800 border-slate-400";
};

const scoreBadge = (isPotential) =>
  isPotential
    ? "bg-cyan-500 text-slate-900 border-cyan-600"
    : "bg-slate-200 text-slate-700 border-slate-300";

const roles = [
  { value: "user", label: "Basic User" },
  { value: "sub_admin", label: "Sub-Admin" },
];

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("stock_auth_token") || "");
  const [me, setMe] = useState(null);

  const [loginUsername, setLoginUsername] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  const [currentPage, setCurrentPage] = useState("home");

  const [minScore, setMinScore] = useState(60);
  const [multibaggerData, setMultibaggerData] = useState(null);
  const [multibaggerLoading, setMultibaggerLoading] = useState(false);
  const [multibaggerError, setMultibaggerError] = useState("");

  const [fnoData, setFnoData] = useState(null);
  const [fnoLoading, setFnoLoading] = useState(false);
  const [fnoError, setFnoError] = useState("");
  const [customScript, setCustomScript] = useState("");
  const [customBuyPrice, setCustomBuyPrice] = useState("");
  const [customPositionLoading, setCustomPositionLoading] = useState(false);
  const [customPositionError, setCustomPositionError] = useState("");
  const [customPositions, setCustomPositions] = useState([]);
  const [sellDialogOpen, setSellDialogOpen] = useState(false);
  const [sellDialogPosition, setSellDialogPosition] = useState(null);
  const [sellPriceInput, setSellPriceInput] = useState("");
  const [sellConfirmChecked, setSellConfirmChecked] = useState(false);
  const [sellLoading, setSellLoading] = useState(false);
  const urgentBuzzedRef = useRef(new Set());
  const audioContextRef = useRef(null);
  const [alertSoundEnabled, setAlertSoundEnabled] = useState(false);
  const [showSoundPrompt, setShowSoundPrompt] = useState(false);

  const [portfolioFile, setPortfolioFile] = useState(null);
  const [portfolioRows, setPortfolioRows] = useState([
    { symbol: "", avg_price: "", quantity: "" },
  ]);
  const [portfolioData, setPortfolioData] = useState(null);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState("");

  const [adminUsers, setAdminUsers] = useState([]);
  const [adminError, setAdminError] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminConfig, setAdminConfig] = useState(null);
  const [apiControlsEdit, setApiControlsEdit] = useState({
    kite_data_enabled: true,
    moneycontrol_data_enabled: true,
    strict_live_only: true,
  });
  const [domainForm, setDomainForm] = useState({ domain: "", target_record: "" });
  const [createForm, setCreateForm] = useState({
    username: "",
    role: "user",
    initial_credits: 0,
    quota_limit: 10,
  });
  const [usernameEdit, setUsernameEdit] = useState({});
  const [roleEdit, setRoleEdit] = useState({});
  const [creditEdit, setCreditEdit] = useState({});
  const [quotaEdit, setQuotaEdit] = useState({});

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : {}),
    [token],
  );

  const isAdmin = me?.role === "owner" || me?.role === "sub_admin";
  const isOwner = me?.role === "owner";

  const hydrateMe = async (accessToken) => {
    const response = await axios.get(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    setMe(response.data);
    return response.data;
  };

  useEffect(() => {
    document.title = "AI Trading Dashboard";
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      if (!token) return;
      try {
        await hydrateMe(token);
      } catch {
        localStorage.removeItem("stock_auth_token");
        setToken("");
        setMe(null);
      }
    };
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!token) return undefined;
    loadCustomPositions();
    const timer = setInterval(() => {
      loadCustomPositions();
    }, 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!Array.isArray(customPositions) || customPositions.length === 0) return;
    if (typeof window === "undefined" || document.hidden) return;
    if (!alertSoundEnabled) return;

    const urgentAlerts = new Set(["EXIT_URGENT_TIME", "EXIT_URGENT_LOSS", "RISKY_PREMIUM", "EXIT_NOW_HIGH_LOSS", "EXIT_URGENT_NO_RECOVERY"]);
    const freshUrgent = customPositions.filter((position) => urgentAlerts.has(position.alert) && !urgentBuzzedRef.current.has(position.id));
    if (!freshUrgent.length) return;

    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioCtx();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === "suspended") {
        ctx.resume();
      }
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "square";
      oscillator.frequency.setValueAtTime(980, ctx.currentTime);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.45);
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start();
      oscillator.stop(ctx.currentTime + 0.5);
    } catch {
      // ignore autoplay/audio restrictions
    }

    freshUrgent.forEach((position) => urgentBuzzedRef.current.add(position.id));
  }, [customPositions, alertSoundEnabled]);

  const syncCredits = (credits) => {
    setMe((prev) => (prev ? { ...prev, credits } : prev));
  };

  const loadCustomPositions = async () => {
    if (!token) return;
    try {
      const response = await axios.get(`${API}/fno/custom-positions`, { headers: authHeaders });
      setCustomPositions(response.data || []);
    } catch {
      // keep silent during polling
    }
  };

  const onLogin = async (event) => {
    event.preventDefault();
    setLoginError("");
    setLoginLoading(true);
    try {
      const response = await axios.post(`${API}/auth/access`, { username: loginUsername.trim() });
      localStorage.setItem("stock_auth_token", response.data.token);
      setToken(response.data.token);
      setMe({
        role: response.data.role,
        credits: response.data.credits,
        user_key: response.data.user_key,
        username: response.data.username,
        admin_exempt: response.data.admin_exempt,
      });
      setCurrentPage("home");
      setLoginUsername("");
    } catch (error) {
      setLoginError(error?.response?.data?.detail || "Unable to login");
    } finally {
      setLoginLoading(false);
    }
  };

  const onLogout = async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { headers: authHeaders });
    } catch {
      // ignore
    }
    localStorage.removeItem("stock_auth_token");
    setToken("");
    setMe(null);
    setCurrentPage("home");
    setMultibaggerData(null);
    setFnoData(null);
    setAdminUsers([]);
    setCustomPositions([]);
    setPortfolioData(null);
    setPortfolioFile(null);
  };

  const generateMultibagger = async () => {
    setMultibaggerError("");
    setMultibaggerLoading(true);
    try {
      const response = await axios.post(`${API}/multibagger/generate`, {}, { headers: authHeaders });
      setMultibaggerData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setMultibaggerError(error?.response?.data?.detail || "Unable to generate multibagger list");
    } finally {
      setMultibaggerLoading(false);
    }
  };

  const generateFnoProjection = async (script = "") => {
    setFnoError("");
    setFnoLoading(true);
    try {
      const payload = script ? { custom_script: script.trim().toUpperCase() } : {};
      const response = await axios.post(`${API}/fno/generate`, payload, { headers: authHeaders });
      setFnoData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setFnoError(error?.response?.data?.detail || "Unable to generate F&O projections");
    } finally {
      setFnoLoading(false);
    }
  };

  const createCustomProjection = async (event) => {
    event.preventDefault();
    setCustomPositionError("");
    if (!alertSoundEnabled) {
      setShowSoundPrompt(true);
      return;
    }
    if (!customScript.trim()) {
      setCustomPositionError("Please enter a script or symbol.");
      return;
    }
    const buyPriceNum = Number(customBuyPrice);
    if (!buyPriceNum || buyPriceNum <= 0) {
      setCustomPositionError("Enter a valid buy price.");
      return;
    }

    setCustomPositionLoading(true);
    try {
      const response = await axios.post(
        `${API}/fno/custom-position`,
        {
          script: customScript.trim().toUpperCase(),
          buy_price: buyPriceNum,
        },
        { headers: authHeaders },
      );
      syncCredits(response.data.credits_remaining);
      setCustomBuyPrice("");
      await loadCustomPositions();
    } catch (error) {
      setCustomPositionError(error?.response?.data?.detail || "Unable to create custom projection.");
    } finally {
      setCustomPositionLoading(false);
    }
  };

  const closeCustomProjection = async (positionId) => {
    try {
      await axios.post(
        `${API}/fno/custom-position/${positionId}/close`,
        {},
        { headers: authHeaders },
      );
      await loadCustomPositions();
    } catch (error) {
      setCustomPositionError(error?.response?.data?.detail || "Unable to close custom projection.");
    }
  };

  const openSellDialog = (position) => {
    setSellDialogPosition(position);
    setSellPriceInput("");
    setSellConfirmChecked(false);
    setSellDialogOpen(true);
  };

  const enableAlertSound = async () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) {
        setCustomPositionError("Audio alert is not supported in this browser.");
        return;
      }
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioCtx();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "square";
      oscillator.frequency.setValueAtTime(880, ctx.currentTime);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.1, ctx.currentTime + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start();
      oscillator.stop(ctx.currentTime + 0.3);

      setAlertSoundEnabled(true);
      setShowSoundPrompt(false);
      setCustomPositionError("");
    } catch {
      setCustomPositionError("Unable to enable buzzer. Please check browser audio settings.");
    }
  };

  const submitSoldPosition = async (event) => {
    event.preventDefault();
    if (!sellDialogPosition) return;

    const soldPrice = Number(sellPriceInput);
    if (!soldPrice || soldPrice <= 0) {
      setCustomPositionError("Please enter a valid sold price.");
      return;
    }
    if (!sellConfirmChecked) {
      setCustomPositionError("Please confirm before submitting sold price.");
      return;
    }

    setSellLoading(true);
    setCustomPositionError("");
    try {
      await axios.post(
        `${API}/fno/custom-position/${sellDialogPosition.id}/sell`,
        {
          sold_price: soldPrice,
          confirm: true,
        },
        { headers: authHeaders },
      );
      setSellDialogOpen(false);
      setSellDialogPosition(null);
      setSellPriceInput("");
      setSellConfirmChecked(false);
      await loadCustomPositions();
    } catch (error) {
      setCustomPositionError(error?.response?.data?.detail || "Unable to mark position as sold.");
    } finally {
      setSellLoading(false);
    }
  };

  const updatePortfolioRow = (index, field, value) => {
    setPortfolioRows((prev) =>
      prev.map((row, idx) => (idx === index ? { ...row, [field]: value } : row)),
    );
  };

  const addPortfolioRow = () => {
    setPortfolioRows((prev) => [...prev, { symbol: "", avg_price: "", quantity: "" }]);
  };

  const removePortfolioRow = (index) => {
    setPortfolioRows((prev) => {
      if (prev.length === 1) return prev;
      return prev.filter((_, idx) => idx !== index);
    });
  };

  const submitManualPortfolio = async (event) => {
    event.preventDefault();
    setPortfolioError("");
    const payloadRows = portfolioRows
      .map((row) => ({
        symbol: row.symbol.trim().toUpperCase(),
        avg_price: Number(row.avg_price),
        quantity: Number(row.quantity),
      }))
      .filter((row) => row.symbol && row.avg_price > 0 && row.quantity > 0);

    if (!payloadRows.length) {
      setPortfolioError("Please add at least one valid portfolio row.");
      return;
    }

    setPortfolioLoading(true);
    try {
      const response = await axios.post(
        `${API}/portfolio/analyze`,
        { positions: payloadRows },
        { headers: authHeaders },
      );
      setPortfolioData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setPortfolioError(error?.response?.data?.detail || "Unable to analyze portfolio.");
    } finally {
      setPortfolioLoading(false);
    }
  };

  const submitUploadedPortfolio = async () => {
    setPortfolioError("");
    if (!portfolioFile) {
      setPortfolioError("Please choose a portfolio file first.");
      return;
    }

    setPortfolioLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", portfolioFile);
      const response = await axios.post(`${API}/portfolio/analyze-upload`, formData, {
        headers: {
          ...authHeaders,
        },
      });
      setPortfolioData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setPortfolioError(error?.response?.data?.detail || "Unable to parse uploaded file.");
    } finally {
      setPortfolioLoading(false);
    }
  };

  const loadAdminUsers = async () => {
    setAdminLoading(true);
    setAdminError("");
    try {
      const response = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      const rows = response.data || [];
      setAdminUsers(rows);
      const creditMap = {};
      const quotaMap = {};
      const usernameMap = {};
      const roleMap = {};
      rows.forEach((row) => {
        creditMap[row.user_key] = row.credits;
        quotaMap[row.user_key] = row.quota_limit;
        usernameMap[row.user_key] = row.username;
        roleMap[row.user_key] = row.role;
      });
      setCreditEdit(creditMap);
      setQuotaEdit(quotaMap);
      setUsernameEdit(usernameMap);
      setRoleEdit(roleMap);
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to load users");
    } finally {
      setAdminLoading(false);
    }
  };

  const loadAdminConfig = async () => {
    try {
      const response = await axios.get(`${API}/admin/config`, { headers: authHeaders });
      setAdminConfig(response.data);
      if (response.data?.api_controls) {
        setApiControlsEdit(response.data.api_controls);
      }
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to load admin config");
    }
  };

  const createUser = async (event) => {
    event.preventDefault();
    setAdminError("");
    try {
      await axios.post(`${API}/admin/users`, createForm, { headers: authHeaders });
      setCreateForm({ username: "", role: "user", initial_credits: 0, quota_limit: 10 });
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to create user");
    }
  };

  const updateCredits = async (userRef) => {
    try {
      await axios.patch(
        `${API}/admin/users/${userRef}/credits`,
        { credits: Number(creditEdit[userRef] || 0) },
        { headers: authHeaders },
      );
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update credits");
    }
  };

  const updateQuota = async (userRef) => {
    try {
      await axios.patch(
        `${API}/admin/users/${userRef}/quota`,
        { quota_limit: Number(quotaEdit[userRef] || 1) },
        { headers: authHeaders },
      );
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update quota");
    }
  };

  const updateUserProfile = async (userRef) => {
    try {
      await axios.patch(
        `${API}/admin/users/${userRef}/profile`,
        {
          username: (usernameEdit[userRef] || "").trim(),
          role: roleEdit[userRef],
        },
        { headers: authHeaders },
      );
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update user profile");
    }
  };

  const updateOwnUsername = async () => {
    try {
      await axios.patch(
        `${API}/admin/self/username`,
        { username: (usernameEdit[me?.user_key] || "").trim() },
        { headers: authHeaders },
      );
      await hydrateMe(token);
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update own username");
    }
  };

  const saveApiControls = async () => {
    try {
      await axios.patch(`${API}/admin/api-controls`, apiControlsEdit, { headers: authHeaders });
      await loadAdminConfig();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update API controls");
    }
  };

  const addDomainMapping = async (event) => {
    event.preventDefault();
    try {
      await axios.post(`${API}/admin/domain-mappings`, domainForm, { headers: authHeaders });
      setDomainForm({ domain: "", target_record: "" });
      await loadAdminConfig();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to save domain mapping");
    }
  };

  const updateDomainStatus = async (domain, status) => {
    try {
      await axios.patch(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}`, { status }, { headers: authHeaders });
      await loadAdminConfig();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update domain status");
    }
  };

  const deleteUser = async (userRef) => {
    try {
      await axios.delete(`${API}/admin/users/${userRef}`, { headers: authHeaders });
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to delete user");
    }
  };

  const filteredMultibaggers = useMemo(() => {
    const rows = multibaggerData?.candidates || [];
    return rows.filter((row) => row.multibagger_score >= minScore);
  }, [multibaggerData, minScore]);

  if (!token || !me) {
    return (
      <main className="min-h-screen dashboard-dark-bg text-slate-100" data-testid="login-page">
        <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-4 py-10">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-cyan-500/40 bg-cyan-500/10 px-4 py-1 text-xs text-cyan-300" data-testid="login-chip">
            <Sparkles size={14} />
            TRADING RESEARCH PLATFORM
          </div>

          <h1 className="text-center text-4xl font-extrabold tracking-tight text-white sm:text-5xl lg:text-6xl" data-testid="login-title">
            Secure Access Dashboard
          </h1>

          <p className="mt-4 max-w-3xl text-center text-sm text-slate-300 sm:text-base" data-testid="login-subtitle">
            Login with your username credential. Public registration is disabled — users are created only by Admin/Owner.
          </p>

          <form onSubmit={onLogin} className="mt-8 w-full max-w-md space-y-3" data-testid="login-form">
            <Input
              value={loginUsername}
              onChange={(event) => setLoginUsername(event.target.value)}
              placeholder="Enter Username"
              className="h-11 border-slate-700 bg-slate-950 text-white placeholder:text-slate-400"
              data-testid="login-username-input"
            />
            <Button
              type="submit"
              className="h-11 w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400"
              data-testid="login-submit-button"
            >
              <KeyRound size={16} />
              {loginLoading ? "Signing in..." : "Login"}
            </Button>
            {loginError ? <p className="text-sm text-rose-400" data-testid="login-error">{loginError}</p> : null}
          </form>

          <Card className="mt-8 w-full max-w-4xl border-cyan-500/20 bg-slate-950/70" data-testid="login-disclaimer-card">
            <CardContent className="pt-5">
              <p className="text-sm font-semibold text-cyan-300">Personal Testing & Educational Disclaimer (SEBI-aligned)</p>
              <p className="mt-2 text-xs leading-relaxed text-slate-300">
                This dashboard is for personal testing and educational analytics only. It does not provide investment advice,
                assured returns, or recommendation service. Please consult a SEBI-registered advisor before real trading.
              </p>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen dashboard-dark-bg text-slate-100" data-testid="app-shell">
      <div className="dashboard-grid-overlay" />
      <div className="relative z-10 mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6 rounded-2xl border border-slate-800 bg-slate-950/70 p-4 shadow-lg" data-testid="app-header">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-cyan-300">AI Trading Dashboard</p>
              <h1 className="text-2xl font-bold text-white sm:text-3xl">Multibagger & F&O Projections</h1>
            </div>
            <Button
              type="button"
              onClick={onLogout}
              className="border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"
              data-testid="logout-button"
            >
              <LogOut size={16} />
              Logout
            </Button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-username">
              <p className="text-xs text-slate-400">Username</p>
              <p className="font-mono text-sm text-cyan-300">{me.username}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-role">
              <p className="text-xs text-slate-400">Role</p>
              <p className="font-mono text-sm text-cyan-300">{me.role}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-credits">
              <p className="text-xs text-slate-400">Credits</p>
              <p className="font-mono text-sm text-cyan-300">{me.admin_exempt ? "EXEMPT" : me.credits}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3" data-testid="summary-cost-note">
              <p className="text-xs text-slate-400">Generation Cost</p>
              <p className="font-mono text-sm text-cyan-300">Multibagger:2 | F&O:2 | Custom F&O:1 | Portfolio:0.2/stock</p>
            </div>
          </div>
        </header>

        <nav className="mb-6 flex flex-wrap gap-3" data-testid="persistent-nav">
          <Button
            type="button"
            onClick={() => setCurrentPage("home")}
            className={currentPage === "home" ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400" : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"}
            data-testid="nav-home"
          >
            <Home size={16} /> Home
          </Button>
          <Button
            type="button"
            onClick={() => setCurrentPage("multibagger")}
            className={currentPage === "multibagger" ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400" : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"}
            data-testid="nav-multibagger"
          >
            <BarChart3 size={16} /> Multibagger
          </Button>
          <Button
            type="button"
            onClick={() => setCurrentPage("fno")}
            className={currentPage === "fno" ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400" : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"}
            data-testid="nav-fno-projections"
          >
            <TrendingUp size={16} /> F&O Projections
          </Button>
          <Button
            type="button"
            onClick={() => setCurrentPage("portfolio")}
            className={currentPage === "portfolio" ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400" : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"}
            data-testid="nav-portfolio"
          >
            <FileUp size={16} /> Portfolio
          </Button>
          {isAdmin ? (
            <Button
              type="button"
              onClick={() => {
                setCurrentPage("admin");
                loadAdminUsers();
                if (isOwner) {
                  loadAdminConfig();
                }
              }}
              className={currentPage === "admin" ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400" : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"}
              data-testid="nav-admin"
            >
              <Shield size={16} /> Admin
            </Button>
          ) : null}
        </nav>

        {currentPage === "home" ? (
          <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6" data-testid="home-landing-dashboard">
            <h2 className="mb-6 text-2xl font-bold text-white">Landing Dashboard</h2>
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              <Card
                className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400"
                onClick={() => setCurrentPage("multibagger")}
                data-testid="home-module-multibagger"
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-cyan-300">
                    <BarChart3 size={18} /> Multibagger
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-300">
                    Discover potential multibagger stocks with RSI, GTT buy levels, and projected upside tables.
                  </p>
                </CardContent>
              </Card>

              <Card
                className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400"
                onClick={() => setCurrentPage("fno")}
                data-testid="home-module-fno"
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-cyan-300">
                    <TrendingUp size={18} /> F&O Projections
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-300">
                    Run live NIFTY/BANKNIFTY projections with assured vs non-directional strategy separation.
                  </p>
                </CardContent>
              </Card>

              <Card
                className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400"
                onClick={() => setCurrentPage("portfolio")}
                data-testid="home-module-portfolio"
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-cyan-300">
                    <FileUp size={18} /> Portfolio Analysis
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-300">
                    Upload holdings or enter manually to get per-stock upside/downside horizon analysis.
                  </p>
                </CardContent>
              </Card>
            </div>
          </section>
        ) : null}

        {currentPage === "multibagger" ? (
          <section className="space-y-6" data-testid="multibagger-page">
            <Card className="result-card border-slate-800 bg-slate-950/70">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">Multibagger Discovery</CardTitle>
                <Button
                  type="button"
                  onClick={generateMultibagger}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="multibagger-generate-button"
                >
                  <RefreshCw size={16} className={multibaggerLoading ? "animate-spin" : ""} />
                  {multibaggerLoading ? "Finding..." : "Find Multibagger (-2)"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="max-w-xl" data-testid="multibagger-slider-block">
                  <Slider
                    min={0}
                    max={100}
                    step={1}
                    value={[minScore]}
                    onValueChange={(value) => setMinScore(value[0])}
                    data-testid="multibagger-score-slider"
                  />
                </div>
                <p className="text-sm text-slate-300" data-testid="multibagger-score-note">
                  Minimum score: <span className="font-mono text-cyan-300">{minScore}</span>
                </p>
                {multibaggerError ? <p className="text-sm text-rose-400" data-testid="multibagger-error">{multibaggerError}</p> : null}
                {!multibaggerData ? (
                  <p className="text-sm text-slate-400" data-testid="multibagger-empty-note">
                    Nothing shown yet. Click <strong>Find Multibagger (-2)</strong> to run live analysis.
                  </p>
                ) : (
                  <p className="text-xs text-slate-400" data-testid="multibagger-refreshed-at">
                    Refreshed at: {formatTime(multibaggerData.analysis_refreshed_at)} | Charged: {multibaggerData.cost_charged}
                  </p>
                )}
              </CardContent>
            </Card>

            {multibaggerData ? (
              <Card className="result-card border-slate-800 bg-slate-950/70">
                <CardHeader>
                  <CardTitle className="text-white">Projected Multibagger Table</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-800" data-testid="multibagger-table-wrapper">
                    <Table data-testid="multibagger-table">
                      <TableHeader className="bg-slate-900">
                        <TableRow>
                          <TableHead>Stock</TableHead>
                          <TableHead>Sector</TableHead>
                          <TableHead>RSI</TableHead>
                          <TableHead>GTT Buy</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>1W</TableHead>
                          <TableHead>1M</TableHead>
                          <TableHead>3M</TableHead>
                          <TableHead>6M</TableHead>
                          <TableHead>9M</TableHead>
                          <TableHead>1Y</TableHead>
                          <TableHead>Score</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredMultibaggers.map((row) => (
                          <Fragment key={`fragment-${row.symbol}`}>
                            <TableRow key={`${row.symbol}-target`} className="result-row" data-testid={`multibagger-target-row-${row.symbol.toLowerCase()}`}>
                              <TableCell className="font-mono text-cyan-300">{row.company_name}</TableCell>
                              <TableCell>{row.sector}</TableCell>
                              <TableCell className="font-mono">{formatNumber(row.current_rsi_level)}</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.gtt_buy_price)}</TableCell>
                              <TableCell className="text-slate-400">Targeted Upside Price</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["1W"])}</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["1M"])}</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["3M"])}</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["6M"])}</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["9M"])}</TableCell>
                              <TableCell className="font-mono">₹{formatNumber(row.targeted_upside_price?.["1Y"])}</TableCell>
                              <TableCell>
                                <Badge className={`border ${scoreBadge(row.is_potential_multibagger)}`}>
                                  {row.multibagger_score}
                                </Badge>
                              </TableCell>
                            </TableRow>

                            <TableRow key={`${row.symbol}-roi`} className="result-row" data-testid={`multibagger-roi-row-${row.symbol.toLowerCase()}`}>
                              <TableCell className="font-mono text-slate-400">{row.symbol}</TableCell>
                              <TableCell className="text-slate-500">Tier: {row.tier_pass_count}/8</TableCell>
                              <TableCell className="text-slate-500">LTP: ₹{formatNumber(row.ltp)}</TableCell>
                              <TableCell className="text-slate-500">PE: {formatNumber(row.pe_ratio)}</TableCell>
                              <TableCell className="text-slate-400">% Profit</TableCell>
                              <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["1W"])}%</TableCell>
                              <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["1M"])}%</TableCell>
                              <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["3M"])}%</TableCell>
                              <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["6M"])}%</TableCell>
                              <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["9M"])}%</TableCell>
                              <TableCell className="font-mono text-emerald-300">{formatNumber(row.targeted_upside_profit_pct?.["1Y"])}%</TableCell>
                              <TableCell>
                                <Badge className={`border ${scoreBadge(row.is_potential_multibagger)}`}>
                                  {row.is_potential_multibagger ? "POTENTIAL" : "WATCH"}
                                </Badge>
                              </TableCell>
                            </TableRow>

                            <TableRow key={`${row.symbol}-thesis`} className="result-row" data-testid={`multibagger-thesis-row-${row.symbol.toLowerCase()}`}>
                              <TableCell colSpan={12} className="text-xs text-slate-300">
                                Thesis: {row.thesis || "No thesis available"}
                              </TableCell>
                            </TableRow>
                          </Fragment>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </section>
        ) : null}

        {currentPage === "fno" ? (
          <section className="space-y-6" data-testid="fno-page">
            <Card className="result-card border-slate-800 bg-slate-950/70">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">F&O Projections</CardTitle>
                <Button
                  type="button"
                  onClick={() => generateFnoProjection()}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="fno-generate-button"
                >
                  <RefreshCw size={16} className={fnoLoading ? "animate-spin" : ""} />
                  {fnoLoading ? "Generating..." : "Generate F&O Projections (-2)"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                <form
                  onSubmit={createCustomProjection}
                  className="flex flex-col gap-3 lg:flex-row"
                  data-testid="fno-custom-script-form"
                >
                  <Input
                    value={customScript}
                    onChange={(event) => setCustomScript(event.target.value.toUpperCase())}
                    placeholder="Custom script/symbol (e.g. NIFTY10MAR26500PE / RELIANCE)"
                    className="font-mono border-slate-700 bg-slate-900 text-slate-100"
                    data-testid="fno-custom-script-input"
                  />
                  <Input
                    value={customBuyPrice}
                    onChange={(event) => setCustomBuyPrice(event.target.value)}
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Buy Price"
                    className="w-full border-slate-700 bg-slate-900 text-slate-100 lg:w-44"
                    data-testid="fno-custom-buy-price-input"
                  />
                  <Button
                    type="submit"
                    className="border border-slate-700 bg-slate-900 text-yellow-200 hover:bg-yellow-200 hover:text-slate-900"
                    data-testid="fno-custom-script-submit"
                  >
                    {customPositionLoading ? "Saving..." : "RUN CUSTOM PROJECTION (-1)"}
                  </Button>
                </form>
                <div className="flex items-center gap-2 text-xs text-slate-300" data-testid="fno-alert-sound-control">
                  <Button
                    type="button"
                    onClick={enableAlertSound}
                    className="h-8 border border-cyan-500/60 bg-cyan-500/10 px-3 text-cyan-200 hover:bg-cyan-500/20"
                    data-testid="enable-alert-buzzer-button"
                  >
                    {alertSoundEnabled ? "Buzzer Enabled" : "Enable Alert Buzzer"}
                  </Button>
                  <span>
                    System can buzz alert during unfortunate trades / urgent exit conditions.
                  </span>
                </div>
                {showSoundPrompt ? (
                  <div className="rounded-md border border-cyan-500/40 bg-cyan-500/10 p-3 text-xs text-cyan-100" data-testid="sound-permission-note">
                    <p className="mb-2 font-semibold">Enable alert sound before custom projection?</p>
                    <p className="mb-2">For urgent trade reversals and high-loss exit alerts, buzzer sound will be triggered.</p>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        onClick={enableAlertSound}
                        className="h-8 bg-cyan-500 px-3 text-slate-900 hover:bg-cyan-400"
                        data-testid="sound-permission-enable"
                      >
                        Allow Buzzer
                      </Button>
                      <Button
                        type="button"
                        onClick={() => {
                          setAlertSoundEnabled(false);
                          setShowSoundPrompt(false);
                        }}
                        className="h-8 border border-slate-600 bg-transparent px-3 text-slate-300 hover:bg-slate-800"
                        data-testid="sound-permission-skip"
                      >
                        Continue Without Sound
                      </Button>
                    </div>
                  </div>
                ) : null}
                {customPositionError ? (
                  <p className="text-sm text-rose-400" data-testid="fno-custom-position-error">{customPositionError}</p>
                ) : null}
                <div className="space-y-3" data-testid="custom-position-list">
                  {customPositions.length ? (
                    customPositions.map((position) => {
                      const urgent = [
                        "EXIT_URGENT_TIME",
                        "EXIT_URGENT_LOSS",
                        "RISKY_PREMIUM",
                        "EXIT_NOW_HIGH_LOSS",
                        "EXIT_URGENT_NO_RECOVERY",
                      ].includes(position.alert || "");
                      const exitPrice = position.best_exit_price ?? position.projected_exit_price;
                      const ltpDeltaClass = Number(position.buy_to_ltp_diff || 0) >= 0 ? "text-emerald-300" : "text-rose-300";
                      return (
                        <div
                          key={position.id}
                          className={`result-card result-hover rounded-lg border p-3 ${urgent ? "urgent-alert-card" : "border-slate-700"}`}
                          data-testid={`custom-position-card-${position.id}`}
                        >
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <p className="font-mono text-yellow-200" data-testid={`custom-position-script-${position.id}`}>{position.script}</p>
                            {position.status === "OPEN" ? (
                              <Button
                                type="button"
                                onClick={() => closeCustomProjection(position.id)}
                                className="h-7 border border-rose-500 bg-transparent px-2 text-rose-300 hover:bg-rose-500/20"
                                data-testid={`custom-position-close-${position.id}`}
                              >
                                <X size={14} />
                              </Button>
                            ) : (
                              <Badge className="border border-emerald-600 bg-emerald-500/20 text-emerald-200" data-testid={`custom-position-status-${position.id}`}>
                                {position.status}
                              </Badge>
                            )}
                          </div>
                          <div className="grid grid-cols-1 gap-1 text-xs md:grid-cols-2">
                            <p>Buy Price: <span className="font-mono">₹{formatNumber(position.buy_price)}</span></p>
                            <p>
                              Live LTP: <span className="font-mono text-sm font-extrabold text-cyan-200" data-testid={`custom-position-live-ltp-${position.id}`}>₹{formatNumber(position.latest_option_ltp)}</span>
                            </p>
                            <p>
                              LTP vs Buy: <span className={`font-mono font-semibold ${ltpDeltaClass}`} data-testid={`custom-position-buy-diff-${position.id}`}>{formatSignedInr(position.buy_to_ltp_diff)}</span>
                            </p>
                            <p>Target1 / Target2: <span className="font-mono">₹{formatNumber(position.target1)} / ₹{formatNumber(position.target2)}</span></p>
                            <p>
                              To T1 / T2: <span className="font-mono" data-testid={`custom-position-target-diff-${position.id}`}>₹{formatNumber(position.ltp_to_t1_diff)} / ₹{formatNumber(position.ltp_to_t2_diff)}</span>
                            </p>
                            <p>Expiry in: <span className="font-mono">{position.minutes_to_expiry} min</span></p>
                            <p>Recovery Potential: <span className="font-mono" data-testid={`custom-position-recovery-${position.id}`}>{position.recovery_potential !== null && position.recovery_potential !== undefined ? `${formatNumber(position.recovery_potential * 100)}%` : "-"}</span></p>
                            <p>
                              T1 Status: <span className="inline-flex items-center gap-1 font-semibold" data-testid={`custom-position-t1-status-${position.id}`}>{position.target1_achieved ? <><CheckCircle2 size={14} className="text-emerald-400" /> Achieved</> : "Pending"}</span>
                            </p>
                            <p>
                              T2 Status: <span className="inline-flex items-center gap-1 font-semibold" data-testid={`custom-position-t2-status-${position.id}`}>{position.target2_achieved ? <><CheckCircle2 size={14} className="text-emerald-400" /> Achieved</> : "Pending"}</span>
                            </p>
                            <p className="md:col-span-2">Exit Plan: <span className="font-mono">{position.revised_exit_plan}</span></p>
                            {position.sold_price !== null && position.sold_price !== undefined ? (
                              <p className="md:col-span-2" data-testid={`custom-position-realized-pnl-${position.id}`}>
                                Sold @ <span className="font-mono">₹{formatNumber(position.sold_price)}</span> | Realized P&L: <span className={`font-mono font-bold ${Number(position.realized_pnl || 0) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{formatSignedInr(position.realized_pnl)}</span>
                              </p>
                            ) : null}
                          </div>
                          {position.can_sell ? (
                            <div className="mt-2">
                              <Button
                                type="button"
                                onClick={() => openSellDialog(position)}
                                className="h-8 border border-emerald-500 bg-emerald-500/10 px-3 text-emerald-200 hover:bg-emerald-500/20"
                                data-testid={`custom-position-sold-button-${position.id}`}
                              >
                                Sold
                              </Button>
                            </div>
                          ) : null}
                          {urgent ? (
                            <div className="mt-2 flex items-center gap-2 rounded-md border border-red-500 bg-red-500/20 px-2 py-1 text-xs font-bold text-red-100" data-testid={`custom-position-alert-${position.id}`}>
                              <AlertTriangle size={14} />
                              URGENT EXIT ALERT — Review this position now
                            </div>
                          ) : null}
                          {(position.alert === "EXIT_NOW_HIGH_LOSS" || position.alert === "EXIT_URGENT_NO_RECOVERY") && exitPrice ? (
                            <p className="mt-2 text-sm font-extrabold text-red-200" data-testid={`custom-position-projected-exit-${position.id}`}>
                              EXIT AT PROJECTED PRICE: ₹{formatNumber(exitPrice)}
                            </p>
                          ) : null}
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-xs text-slate-400" data-testid="custom-position-empty-note">
                      No sticky custom projections yet. Create one using script + buy price.
                    </p>
                  )}
                </div>
                {sellDialogOpen && sellDialogPosition ? (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4" data-testid="custom-position-sell-modal">
                    <Card className="w-full max-w-md border-slate-700 bg-slate-950">
                      <CardHeader>
                        <CardTitle className="text-white">Mark Position as Sold</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <form className="space-y-3" onSubmit={submitSoldPosition} data-testid="custom-position-sell-form">
                          <p className="text-sm text-slate-300">{sellDialogPosition.script}</p>
                          <Input
                            type="number"
                            min="0"
                            step="0.01"
                            value={sellPriceInput}
                            onChange={(event) => setSellPriceInput(event.target.value)}
                            placeholder="Enter Sold Price"
                            data-testid="custom-position-sell-price-input"
                            className="border-slate-700 bg-slate-900 text-slate-100"
                          />
                          <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="custom-position-sell-confirm">
                            <input
                              type="checkbox"
                              checked={sellConfirmChecked}
                              onChange={(event) => setSellConfirmChecked(event.target.checked)}
                              data-testid="custom-position-sell-confirm-checkbox"
                            />
                            I confirm this sold price is correct.
                          </label>
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              type="button"
                              className="border border-slate-600 bg-transparent text-slate-200 hover:bg-slate-800"
                              onClick={() => {
                                setSellDialogOpen(false);
                                setSellDialogPosition(null);
                              }}
                              data-testid="custom-position-sell-cancel"
                            >
                              Cancel
                            </Button>
                            <Button
                              type="submit"
                              className="bg-emerald-500 text-slate-900 hover:bg-emerald-400"
                              disabled={sellLoading}
                              data-testid="custom-position-sell-submit"
                            >
                              {sellLoading ? "Saving..." : "Confirm Sold"}
                            </Button>
                          </div>
                        </form>
                      </CardContent>
                    </Card>
                  </div>
                ) : null}
                {fnoError ? <p className="text-sm text-rose-400" data-testid="fno-error">{fnoError}</p> : null}
                {!fnoData ? (
                  <p className="text-sm text-slate-400" data-testid="fno-empty-note">
                    Nothing shown yet. Click <strong>Generate F&O Projections (-2)</strong> for live analysis.
                  </p>
                ) : (
                  <p className="text-xs text-slate-400" data-testid="fno-refreshed-at">
                    Refreshed at: {formatTime(fnoData.analysis_refreshed_at)} | Charged: {fnoData.cost_charged}
                  </p>
                )}
              </CardContent>
            </Card>

            {fnoData ? (
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
                <div className="space-y-6 xl:col-span-8">
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2" data-testid="fno-dual-pane">
                    {[fnoData.nifty_projection, fnoData.banknifty_projection].map((pane) => (
                      <Card key={pane.index_name} className="result-card border-slate-800 bg-slate-950/70" data-testid={`pane-${pane.index_name.toLowerCase()}`}>
                        <CardHeader>
                          <CardTitle className="flex items-center justify-between gap-2 text-white">
                            <span>{pane.index_name}</span>
                            <Badge className="border border-cyan-500/50 bg-cyan-500/20 text-cyan-200">
                              Spot {formatNumber(pane.spot, 2)}
                            </Badge>
                          </CardTitle>
                          <p className="text-xs text-slate-400" data-testid={`pane-range-${pane.index_name.toLowerCase()}`}>
                            Strike Filter: {formatNumber(pane.strike_range_min, 0)} to {formatNumber(pane.strike_range_max, 0)}
                          </p>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div data-testid={`pane-assured-${pane.index_name.toLowerCase()}`}>
                            <p className="mb-2 text-sm font-semibold text-cyan-300">Assured Directional Projections</p>
                            {pane.assured_signals.length ? (
                              <div className="space-y-2">
                                {pane.assured_signals.slice(0, 5).map((signal) => (
                                  <div key={signal.script} className="result-hover rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                                    <div className="mb-1 flex items-center justify-between">
                                      <span className="font-mono text-cyan-200">{signal.script}</span>
                                      <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                                    </div>
                                    <p>Expiry: {formatExpiryDate(signal.expiry)}</p>
                                    <p>Entry/SL/T1/T2: ₹{formatNumber(signal.entry_price)} / ₹{formatNumber(signal.stop_loss)} / ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                                    <p>Confluence: {signal.confluence_score} ({signal.signal_quality})</p>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400">No assured directional setup currently.</p>
                            )}
                          </div>

                          <div data-testid={`pane-watchlist-${pane.index_name.toLowerCase()}`}>
                            <p className="mb-2 text-sm font-semibold text-emerald-300">Watchlist (Medium Conviction)</p>
                            {pane.watchlist_signals?.length ? (
                              <div className="space-y-2">
                                {pane.watchlist_signals.map((signal) => (
                                  <div key={`${signal.script}-watch`} className="result-hover rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs">
                                    <div className="mb-1 flex items-center justify-between">
                                      <span className="font-mono text-emerald-200">{signal.script}</span>
                                      <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                                    </div>
                                    <p>Expiry: {formatExpiryDate(signal.expiry)}</p>
                                    <p>Entry/SL/T1/T2: ₹{formatNumber(signal.entry_price)} / ₹{formatNumber(signal.stop_loss)} / ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                                    <p>Confluence: {signal.confluence_score} ({signal.signal_quality})</p>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400">No medium-conviction watchlist setup right now.</p>
                            )}
                          </div>

                          <div data-testid={`pane-nondirectional-${pane.index_name.toLowerCase()}`}>
                            <p className="mb-2 text-sm font-semibold text-amber-300">Non-Directional Strategies</p>
                            {pane.non_directional_strategies.length ? (
                              <div className="space-y-2">
                                {pane.non_directional_strategies.map((item) => (
                                  <div key={`${pane.index_name}-${item.strike}`} className="result-hover rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs">
                                    <p className="font-semibold text-amber-200">{item.strategy}</p>
                                    <p>Strike: {formatNumber(item.strike, 0)} | CE: {item.ce_script} | PE: {item.pe_script}</p>
                                    <p>Combined Entry: ₹{formatNumber(item.combined_entry)}</p>
                                    <p>{item.rationale}</p>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400">No CE+PE same-strike conflict currently.</p>
                            )}
                          </div>

                          <div className="grid grid-cols-1 gap-2" data-testid={`pane-reports-${pane.index_name.toLowerCase()}`}>
                            <div className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                              <p className="font-semibold text-cyan-300">With Consolidated Analysis</p>
                              <p>Breadth: {formatNumber(pane.with_consolidated_report.breadth_score)} | Momentum: {formatNumber(pane.with_consolidated_report.momentum_score)} | Bias: {pane.with_consolidated_report.bias}</p>
                              <p>Contributors: {pane.with_consolidated_report.top_contributors.join(" | ")}</p>
                            </div>
                            <div className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                              <p className="font-semibold text-cyan-300">Without Consolidated Analysis</p>
                              <p>Breadth: {formatNumber(pane.without_consolidated_report.breadth_score)} | Momentum: {formatNumber(pane.without_consolidated_report.momentum_score)} | Bias: {pane.without_consolidated_report.bias}</p>
                              <p>Contributors: {pane.without_consolidated_report.top_contributors.join(" | ")}</p>
                            </div>
                          </div>

                          {pane.rejection_note ? (
                            <p
                              className="rounded-md border border-slate-700 bg-slate-900/70 p-2 text-xs font-bold text-white transition-colors hover:text-blue-900"
                              data-testid={`pane-rejection-note-${pane.index_name.toLowerCase()}`}
                            >
                              {pane.rejection_note}
                            </p>
                          ) : null}
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="stock-fno-bottom-panel">
                    <CardHeader>
                      <CardTitle className="text-white">Profitable F&O Signals — Individual Stocks</CardTitle>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {fnoData.stock_signals?.length ? (
                        fnoData.stock_signals.map((signal) => (
                          <div key={signal.script} className="result-hover rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs" data-testid={`stock-fno-signal-${signal.script.toLowerCase()}`}>
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <p className="font-mono text-cyan-200">{signal.script}</p>
                              <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                            </div>
                            <p data-testid={`stock-fno-signal-expiry-${signal.script.toLowerCase()}`}>Expiry: {formatExpiryDate(signal.expiry)} (monthly stock contract)</p>
                            <p>Entry: ₹{formatNumber(signal.entry_price)}</p>
                            <p>SL: ₹{formatNumber(signal.stop_loss)}</p>
                            <p>T1/T2: ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                            <p>Confidence: {signal.confluence_score}</p>
                          </div>
                        ))
                      ) : (
                        <p className="text-sm text-slate-400" data-testid="stock-fno-empty-note">No verified stock option-chain opportunities found in this cycle.</p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                <div className="xl:col-span-4">
                  <div className="sticky top-4 space-y-4">
                    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="top4-trades-panel">
                      <CardHeader>
                        <CardTitle className="text-white">Top 4 Best Trade Now</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        {fnoData.top_trades?.length ? (
                          fnoData.top_trades.map((trade) => (
                            <div key={trade.script} className="result-hover rounded-md border border-slate-800 bg-slate-900/70 p-3 text-xs" data-testid={`top4-trade-${trade.script.toLowerCase()}`}>
                              <div className="mb-2 flex items-center justify-between">
                                <p className="font-mono text-cyan-200">{trade.script}</p>
                                <Badge className={`border ${qualityBadge(trade.signal_quality)}`}>{trade.signal_quality}</Badge>
                              </div>
                              <p>Entry: ₹{formatNumber(trade.entry_price)}</p>
                              <p>SL: ₹{formatNumber(trade.stop_loss)}</p>
                              <p>T1/T2: ₹{formatNumber(trade.target1)} / ₹{formatNumber(trade.target2)}</p>
                              <p>Confidence: {trade.confluence_score} | {trade.direction}</p>
                              <p className="text-slate-400">{(trade.trigger_factors || []).slice(0, 2).join(" | ")}</p>
                            </div>
                          ))
                        ) : (
                          <p className="text-sm text-slate-400">Generate projections to populate Top 4 trades.</p>
                        )}
                      </CardContent>
                    </Card>

                    {fnoData.custom_signal ? (
                      <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="custom-script-result-card">
                        <CardHeader>
                          <CardTitle className="text-white">Custom Script Result</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-1 text-xs">
                          <p className="font-mono text-cyan-200">{fnoData.custom_signal.script}</p>
                          <p>Direction: {fnoData.custom_signal.direction}</p>
                          <p>Entry/SL/T1/T2: ₹{formatNumber(fnoData.custom_signal.entry_price)} / ₹{formatNumber(fnoData.custom_signal.stop_loss)} / ₹{formatNumber(fnoData.custom_signal.target1)} / ₹{formatNumber(fnoData.custom_signal.target2)}</p>
                          <p>Confluence: {fnoData.custom_signal.confluence_score}</p>
                        </CardContent>
                      </Card>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {currentPage === "portfolio" ? (
          <section className="space-y-6" data-testid="portfolio-page">
            <Card className="result-card border-slate-800 bg-slate-950/70">
              <CardHeader>
                <CardTitle className="text-white">Portfolio Analysis</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <div className="space-y-3">
                  <p className="text-sm text-slate-200">Upload Portfolio File (.txt, .csv, .xls, .xlsx, .pdf, .jpg, .jpeg, .bmp, .png, .webp)</p>
                  <Input
                    type="file"
                    accept=".txt,.csv,.CSV,text/csv,application/csv,application/vnd.ms-excel,.xls,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.pdf,application/pdf,.jpg,.jpeg,.bmp,.png,.webp,image/*"
                    onChange={(event) => setPortfolioFile(event.target.files?.[0] || null)}
                    className="border-slate-700 bg-slate-900 text-slate-100"
                    data-testid="portfolio-file-input"
                  />
                  <Button
                    type="button"
                    onClick={submitUploadedPortfolio}
                    className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                    data-testid="portfolio-upload-submit"
                  >
                    <FileUp size={16} /> Analyze Uploaded Portfolio (0.2 per parsed stock)
                  </Button>
                </div>

                <form className="space-y-3" onSubmit={submitManualPortfolio} data-testid="portfolio-manual-form">
                  <p className="text-sm text-slate-200">Manual Portfolio Entry</p>
                  {portfolioRows.map((row, index) => (
                    <div key={`portfolio-row-${index}`} className="grid grid-cols-12 gap-2" data-testid={`portfolio-manual-row-${index}`}>
                      <Input
                        value={row.symbol}
                        onChange={(event) => updatePortfolioRow(index, "symbol", event.target.value.toUpperCase())}
                        placeholder="Symbol"
                        className="col-span-4 border-slate-700 bg-slate-900 text-slate-100"
                        data-testid={`portfolio-row-symbol-${index}`}
                      />
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={row.avg_price}
                        onChange={(event) => updatePortfolioRow(index, "avg_price", event.target.value)}
                        placeholder="Avg Price"
                        className="col-span-3 border-slate-700 bg-slate-900 text-slate-100"
                        data-testid={`portfolio-row-avg-${index}`}
                      />
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={row.quantity}
                        onChange={(event) => updatePortfolioRow(index, "quantity", event.target.value)}
                        placeholder="Qty"
                        className="col-span-3 border-slate-700 bg-slate-900 text-slate-100"
                        data-testid={`portfolio-row-qty-${index}`}
                      />
                      <div className="col-span-2 flex gap-1">
                        <Button
                          type="button"
                          onClick={addPortfolioRow}
                          className="h-10 w-10 bg-cyan-500 p-0 text-slate-900 hover:bg-cyan-400"
                          data-testid={`portfolio-row-add-${index}`}
                        >
                          <Plus size={14} />
                        </Button>
                        <Button
                          type="button"
                          onClick={() => removePortfolioRow(index)}
                          className="h-10 w-10 border border-rose-600 bg-transparent p-0 text-rose-300 hover:bg-rose-500/20"
                          data-testid={`portfolio-row-remove-${index}`}
                        >
                          <Minus size={14} />
                        </Button>
                      </div>
                    </div>
                  ))}

                  <Button
                    type="submit"
                    className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                    data-testid="portfolio-manual-submit"
                  >
                    Submit Portfolio (0.2 per stock)
                  </Button>
                </form>
              </CardContent>
            </Card>

            {portfolioError ? (
              <p className="text-sm text-rose-400" data-testid="portfolio-error">{portfolioError}</p>
            ) : null}
            {portfolioLoading ? (
              <p className="text-sm text-cyan-300" data-testid="portfolio-loading">Analyzing portfolio...</p>
            ) : null}
            {portfolioData ? (
              <p className="text-xs text-slate-300" data-testid="portfolio-charge-info">
                Charged: {portfolioData.cost_charged} | Credits Remaining: {portfolioData.credits_remaining}
              </p>
            ) : null}

            {portfolioData?.stocks?.length ? (
              <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="portfolio-results-card">
                <CardHeader>
                  <CardTitle className="text-white">Portfolio Analysis Results</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {portfolioData.stocks.map((stock) => (
                    <div key={stock.symbol} className="result-hover rounded-lg border border-slate-800 bg-slate-900/70 p-4" data-testid={`portfolio-stock-${stock.symbol.toLowerCase()}`}>
                      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <p className="font-mono text-base text-cyan-200">{stock.symbol} — {stock.company_name}</p>
                        <Badge className={`border ${stock.recommendation.includes("High risk") ? "bg-rose-600 text-white" : "bg-cyan-500 text-slate-900"}`}>
                          {stock.recommendation}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-200">Sector: {stock.sector} | LTP: ₹{formatNumber(stock.ltp)} | Avg: ₹{formatNumber(stock.avg_price)} | Qty: {formatNumber(stock.quantity, 0)} | Allocation: {formatNumber(stock.allocation_pct)}% | PnL: {formatNumber(stock.pnl_pct)}%</p>
                      <p className="mt-1 text-xs text-slate-200">Value: {stock.value_flag} | Price Zone: {stock.price_zone} | Momentum: {stock.momentum_proxy} | Quality: {stock.quality_proxy}</p>

                      <div className="mt-3 overflow-auto">
                        <Table data-testid={`portfolio-horizon-table-${stock.symbol.toLowerCase()}`}>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Horizon</TableHead>
                              <TableHead>Max Expected Price</TableHead>
                              <TableHead>Amount (+/-)</TableHead>
                              <TableHead>Percent (+/-)</TableHead>
                              <TableHead>Signal</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {Object.entries(stock.expected_signals || {}).map(([horizon, values]) => (
                              <TableRow key={`${stock.symbol}-${horizon}`}>
                                <TableCell>{horizon}</TableCell>
                                <TableCell className="font-mono">₹{formatNumber(values.max_expected_price)}</TableCell>
                                <TableCell className={`font-mono ${values.direction === "PROFIT" ? "text-emerald-300" : "text-rose-300"}`}>{values.amount_signal}</TableCell>
                                <TableCell className={`font-mono ${values.direction === "PROFIT" ? "text-emerald-300" : "text-rose-300"}`}>{values.percent_signal}</TableCell>
                                <TableCell>
                                  <Badge className={`border ${values.direction === "PROFIT" ? "bg-emerald-600 text-white" : "bg-rose-600 text-white"}`}>
                                    {values.direction}
                                  </Badge>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                      <p className="mt-2 text-xs text-yellow-200">{stock.comments}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ) : null}
          </section>
        ) : null}

        {currentPage === "admin" && isAdmin ? (
          <section className="space-y-6" data-testid="admin-page">
            <Card className="result-card border-slate-800 bg-slate-950/70">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">User Management & Security</CardTitle>
                <Button
                  type="button"
                  onClick={loadAdminUsers}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="admin-refresh-users-button"
                >
                  <UserCog size={16} /> Refresh Users
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={createUser} className="grid grid-cols-1 gap-3 md:grid-cols-5" data-testid="admin-create-user-form">
                  <Input
                    value={createForm.username}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, username: event.target.value }))}
                    placeholder="Username"
                    data-testid="admin-create-username"
                    className="border-slate-700 bg-slate-900 text-slate-100"
                  />
                  <select
                    value={createForm.role}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, role: event.target.value }))}
                    className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-slate-100"
                    data-testid="admin-create-role"
                  >
                    {roles.map((role) => (
                      <option key={role.value} value={role.value}>{role.label}</option>
                    ))}
                  </select>
                  <Input
                    type="number"
                    min="0"
                    value={createForm.initial_credits}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, initial_credits: Number(event.target.value) }))}
                    placeholder="Initial Credits"
                    data-testid="admin-create-credits"
                    className="border-slate-700 bg-slate-900 text-slate-100"
                  />
                  <Input
                    type="number"
                    min="1"
                    value={createForm.quota_limit}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, quota_limit: Number(event.target.value) }))}
                    placeholder="Quota"
                    data-testid="admin-create-quota"
                    className="border-slate-700 bg-slate-900 text-slate-100"
                    disabled={createForm.role !== "sub_admin"}
                  />
                  <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-create-submit">
                    Create
                  </Button>
                </form>

                {adminError ? <p className="text-sm text-rose-400" data-testid="admin-error">{adminError}</p> : null}

                {adminLoading ? (
                  <p className="text-sm text-slate-400" data-testid="admin-loading">Loading users...</p>
                ) : (
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-800" data-testid="admin-users-table-wrapper">
                    <Table data-testid="admin-users-table">
                      <TableHeader className="bg-slate-900">
                        <TableRow>
                          <TableHead>Credential</TableHead>
                          <TableHead>Role</TableHead>
                          <TableHead>Credits</TableHead>
                          <TableHead>Quota</TableHead>
                          <TableHead>Created By</TableHead>
                          <TableHead>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {adminUsers.map((row) => (
                          <TableRow key={row.user_key} className="result-row" data-testid={`admin-row-${row.user_key}`}>
                            <TableCell>
                              <Input
                                value={usernameEdit[row.user_key] ?? row.username}
                                onChange={(event) =>
                                  setUsernameEdit((prev) => ({ ...prev, [row.user_key]: event.target.value }))
                                }
                                className="h-8 w-44 border-slate-700 bg-slate-900 text-xs text-cyan-200"
                                data-testid={`admin-username-input-${row.user_key}`}
                                disabled={!isOwner && row.user_key !== me?.user_key}
                              />
                            </TableCell>
                            <TableCell>
                              {isOwner ? (
                                <select
                                  value={roleEdit[row.user_key] ?? row.role}
                                  onChange={(event) =>
                                    setRoleEdit((prev) => ({ ...prev, [row.user_key]: event.target.value }))
                                  }
                                  className="h-8 rounded-md border border-slate-700 bg-slate-900 px-2 text-xs text-slate-100"
                                  data-testid={`admin-role-select-${row.user_key}`}
                                >
                                  <option value="owner">Owner</option>
                                  <option value="sub_admin">Sub-Admin</option>
                                  <option value="user">User</option>
                                </select>
                              ) : (
                                <span>{row.role}</span>
                              )}
                            </TableCell>
                            <TableCell>
                              <Input
                                type="number"
                                min="0"
                                value={creditEdit[row.user_key] ?? row.credits}
                                onChange={(event) =>
                                  setCreditEdit((prev) => ({ ...prev, [row.user_key]: Number(event.target.value) }))
                                }
                                className="h-8 w-24 border-slate-700 bg-slate-900 text-slate-100"
                                data-testid={`admin-credit-input-${row.user_key}`}
                              />
                            </TableCell>
                            <TableCell>
                              {row.role === "sub_admin" ? (
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="number"
                                    min="1"
                                    value={quotaEdit[row.user_key] ?? row.quota_limit}
                                    onChange={(event) =>
                                      setQuotaEdit((prev) => ({ ...prev, [row.user_key]: Number(event.target.value) }))
                                    }
                                    className="h-8 w-24 border-slate-700 bg-slate-900 text-slate-100"
                                    data-testid={`admin-quota-input-${row.user_key}`}
                                    disabled={!isOwner}
                                  />
                                  <span className="text-xs text-slate-400">used {row.quota_used}</span>
                                </div>
                              ) : (
                                <span className="text-xs text-slate-500">-</span>
                              )}
                            </TableCell>
                            <TableCell className="text-xs text-slate-400">{row.created_by}</TableCell>
                            <TableCell className="space-x-2">
                              <Button
                                type="button"
                                onClick={() => updateCredits(row.user_key)}
                                className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700"
                                data-testid={`admin-update-credit-${row.user_key}`}
                              >
                                Update Credits
                              </Button>
                              {isOwner && row.role === "sub_admin" ? (
                                <Button
                                  type="button"
                                  onClick={() => updateQuota(row.user_key)}
                                  className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700"
                                  data-testid={`admin-update-quota-${row.user_key}`}
                                >
                                  Update Quota
                                </Button>
                              ) : null}
                              {isOwner ? (
                                <Button
                                  type="button"
                                  onClick={() => updateUserProfile(row.user_key)}
                                  className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700"
                                  data-testid={`admin-update-profile-${row.user_key}`}
                                >
                                  Update Profile
                                </Button>
                              ) : row.user_key === me?.user_key ? (
                                <Button
                                  type="button"
                                  onClick={updateOwnUsername}
                                  className="h-8 bg-slate-800 px-3 text-xs text-slate-100 hover:bg-slate-700"
                                  data-testid={`admin-update-own-username-${row.user_key}`}
                                >
                                  Update My Login
                                </Button>
                              ) : null}
                              {row.role !== "owner" ? (
                                <Button
                                  type="button"
                                  onClick={() => deleteUser(row.user_key)}
                                  className="h-8 border border-rose-600 bg-transparent px-3 text-xs text-rose-300 hover:bg-rose-500/10"
                                  data-testid={`admin-delete-${row.user_key}`}
                                >
                                  Delete
                                </Button>
                              ) : null}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>

            {isOwner ? (
              <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-advanced-controls-card">
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                  <CardTitle className="text-white">Advanced Controls</CardTitle>
                  <Button
                    type="button"
                    onClick={loadAdminConfig}
                    className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                    data-testid="admin-refresh-config-button"
                  >
                    Refresh Controls
                  </Button>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-kite-enabled">
                      <input
                        type="checkbox"
                        checked={Boolean(apiControlsEdit.kite_data_enabled)}
                        onChange={(event) =>
                          setApiControlsEdit((prev) => ({ ...prev, kite_data_enabled: event.target.checked }))
                        }
                      />
                      Kite data enabled
                    </label>
                    <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-moneycontrol-enabled">
                      <input
                        type="checkbox"
                        checked={Boolean(apiControlsEdit.moneycontrol_data_enabled)}
                        onChange={(event) =>
                          setApiControlsEdit((prev) => ({ ...prev, moneycontrol_data_enabled: event.target.checked }))
                        }
                      />
                      Secondary API enabled
                    </label>
                    <label className="flex items-center gap-2 text-sm text-slate-200" data-testid="api-control-strict-live-only">
                      <input
                        type="checkbox"
                        checked={Boolean(apiControlsEdit.strict_live_only)}
                        onChange={(event) =>
                          setApiControlsEdit((prev) => ({ ...prev, strict_live_only: event.target.checked }))
                        }
                      />
                      Strict live-only mode
                    </label>
                  </div>
                  <Button
                    type="button"
                    onClick={saveApiControls}
                    className="bg-slate-800 text-slate-100 hover:bg-slate-700"
                    data-testid="admin-save-api-controls"
                  >
                    Save API Controls
                  </Button>

                  <form onSubmit={addDomainMapping} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="admin-domain-form">
                    <Input
                      value={domainForm.domain}
                      onChange={(event) => setDomainForm((prev) => ({ ...prev, domain: event.target.value }))}
                      placeholder="Domain or Subdomain (example.com / trade.example.com)"
                      className="border-slate-700 bg-slate-900 text-slate-100"
                      data-testid="admin-domain-input"
                    />
                    <Input
                      value={domainForm.target_record}
                      onChange={(event) => setDomainForm((prev) => ({ ...prev, target_record: event.target.value }))}
                      placeholder="A-Record target (IP/host)"
                      className="border-slate-700 bg-slate-900 text-slate-100"
                      data-testid="admin-domain-target-input"
                    />
                    <Button type="submit" className="bg-slate-800 text-slate-100 hover:bg-slate-700" data-testid="admin-domain-submit">
                      Save Domain Mapping
                    </Button>
                  </form>

                  {adminConfig?.hosting_dns_reference ? (
                    <div className="rounded-md border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300" data-testid="admin-hosting-dns-reference">
                      <p>Hosting Domain: <span className="font-mono text-cyan-300">{adminConfig.hosting_dns_reference.hosting_domain || "-"}</span></p>
                      <p>Resolved IPv4: <span className="font-mono text-cyan-300">{adminConfig.hosting_dns_reference.resolved_ipv4 || "Unavailable"}</span></p>
                      <p>Record Type: <span className="font-mono text-cyan-300">A</span></p>
                      <p>Apex Host Label: <span className="font-mono text-cyan-300">@</span> | Subdomain Host Label Example: <span className="font-mono text-cyan-300">trade</span></p>
                    </div>
                  ) : null}

                  <p className="text-xs text-slate-400" data-testid="admin-dns-note">
                    {adminConfig?.dns_note || "A-record update must be done in your registrar DNS settings."}
                  </p>

                  {(adminConfig?.dns_instructions || []).length ? (
                    <ul className="list-disc space-y-1 pl-5 text-xs text-slate-300" data-testid="admin-dns-instructions-list">
                      {(adminConfig?.dns_instructions || []).map((step, idx) => (
                        <li key={`dns-step-${idx}`}>{step}</li>
                      ))}
                    </ul>
                  ) : null}

                  <div className="space-y-2" data-testid="admin-domain-list">
                    {(adminConfig?.domain_mappings || []).map((row) => (
                      <div key={row.domain} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-800 bg-slate-900/60 p-2">
                        <div className="text-xs text-slate-200">
                          <p><span className="text-slate-400">Domain:</span> {row.domain}</p>
                          <p><span className="text-slate-400">Root:</span> {row.root_domain || "-"} | <span className="text-slate-400">Host:</span> {row.host_label || "@"}</p>
                          <p><span className="text-slate-400">Record:</span> {row.record_type || "A"} → {row.resolved_target_ip || row.target_record}</p>
                          <p><span className="text-slate-400">Target:</span> {row.target_record}</p>
                          <p><span className="text-slate-400">Status:</span> {row.status}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            onClick={() => updateDomainStatus(row.domain, "ACTIVE")}
                            className="h-8 bg-emerald-600 px-3 text-xs text-white hover:bg-emerald-500"
                            data-testid={`admin-domain-active-${row.domain}`}
                          >
                            Mark Active
                          </Button>
                          <Button
                            type="button"
                            onClick={() => updateDomainStatus(row.domain, "FAILED")}
                            className="h-8 bg-rose-600 px-3 text-xs text-white hover:bg-rose-500"
                            data-testid={`admin-domain-failed-${row.domain}`}
                          >
                            Mark Failed
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </section>
        ) : null}

        <footer className="mt-8" data-testid="footer-disclaimer">
          <Card className="border border-cyan-500/20 bg-slate-950/70">
            <CardContent className="pt-5">
              <p className="flex items-center gap-2 text-sm font-semibold text-cyan-300">
                <GaugeCircle size={14} /> Personal Testing & Educational Disclaimer
              </p>
              <p className="mt-2 text-xs leading-relaxed text-slate-300">
                This platform is an educational analytics system for personal testing. Signals, projections, and scorecards are model-based outputs
                and not trading advice. Market participation carries risk. Consult SEBI-registered advisors for investment decisions.
              </p>
            </CardContent>
          </Card>
        </footer>
      </div>
    </main>
  );
}
