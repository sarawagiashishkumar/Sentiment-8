import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Download,
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
import {
  formatNumber, formatTime, formatExpiryDate, formatSignedInr,
  heatmapClass, formatSignedPct, directionBadge, qualityBadge, scoreBadge,
} from "./utils/formatters";
import {
  collectAllFnoSignals, buildExportRow, exportFnoAsCSV, exportFnoAsXLS, exportFnoAsJPG,
  exportFnoAsPDF, exportFnoAsWord,
} from "./utils/exportUtils";
import { LiveInfoBox } from "./components/shared/LiveInfoBox";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

/**
 * Read an NDJSON stream from a fetch Response.
 * Calls onProgress({type, phase, message}) for progress events.
 * Returns the "complete" event's data payload.
 */
async function readNDJSONStream(response, onProgress) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line);
        if (event.type === "progress" && onProgress) {
          onProgress(event);
        } else if (event.type === "complete") {
          result = event.data;
        }
      } catch {
        // skip malformed lines
      }
    }
  }
  // Process any remaining buffer
  if (buffer.trim()) {
    try {
      const event = JSON.parse(buffer);
      if (event.type === "complete") result = event.data;
    } catch {
      // skip
    }
  }
  return result;
}

// Backward-compat wrapper for renderLiveInfoBox calls in JSX
const renderLiveInfoBox = (signal, suffix) => <LiveInfoBox signal={signal} suffix={suffix} />;

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
  const [customMbSymbol, setCustomMbSymbol] = useState("");
  const [customMbResult, setCustomMbResult] = useState(null);
  const [customMbLoading, setCustomMbLoading] = useState(false);
  const [customMbError, setCustomMbError] = useState("");

  const [fnoData, setFnoData] = useState(null);
  const exportTableRef = useRef(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  // Close export menu on outside click
  useEffect(() => {
    if (!exportMenuOpen) return;
    const handler = (e) => {
      if (!e.target.closest("[data-testid='fno-export-btn']") && !e.target.closest("[data-testid='fno-export-menu']")) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportMenuOpen]);
  const [fnoLoading, setFnoLoading] = useState(false);
  const [fnoError, setFnoError] = useState("");
  const [fnoProgress, setFnoProgress] = useState("");
  const [multibaggerProgress, setMultibaggerProgress] = useState("");
  const [customScript, setCustomScript] = useState("");
  const [customBuyPrice, setCustomBuyPrice] = useState("");
  const [customLots, setCustomLots] = useState("1");
  const [customPositionLoading, setCustomPositionLoading] = useState(false);
  const [customPositionError, setCustomPositionError] = useState("");
  const [customPositions, setCustomPositions] = useState([]);
  const [sellDialogOpen, setSellDialogOpen] = useState(false);
  const [sellDialogPosition, setSellDialogPosition] = useState(null);
  const [sellPriceInput, setSellPriceInput] = useState("");
  const [sellConfirmChecked, setSellConfirmChecked] = useState(false);
  const [sellLoading, setSellLoading] = useState(false);
  const urgentBuzzedRef = useRef(new Set());
  const targetBuzzedRef = useRef(new Set());
  const warningBuzzedRef = useRef(new Set());
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
  // CSV Seed Management state
  const [csvSeeds, setCsvSeeds] = useState([]);
  const [csvSeedLoading, setCsvSeedLoading] = useState(false);
  const [csvSeedMsg, setCsvSeedMsg] = useState("");
  const [csvUploadSymbol, setCsvUploadSymbol] = useState("");
  // Macro Events state
  const [macroEventsData, setMacroEventsData] = useState({ active_events: [], all_events: [] });
  const [macroEventsSaving, setMacroEventsSaving] = useState(false);
  const [sectorMomentumData, setSectorMomentumData] = useState(null);
  const [sectorMomentumLoading, setSectorMomentumLoading] = useState(false);
  const [sectorMomentumError, setSectorMomentumError] = useState("");
  const [expandedMbBands, setExpandedMbBands] = useState({});
  const [apiControlsEdit, setApiControlsEdit] = useState({
    kite_data_enabled: true,
    moneycontrol_data_enabled: true,
    strict_live_only: true,
  });
  const [domainForm, setDomainForm] = useState({ domain: "", target_record: "" });
  const [domainDeleteConfirm, setDomainDeleteConfirm] = useState(null); // domain string to confirm
  const [domainMapStatus, setDomainMapStatus] = useState({}); // { domain: {loading, result} }
  const [expandedDnsInstructions, setExpandedDnsInstructions] = useState({}); // { domain: bool }
  const [kiteStatus, setKiteStatus] = useState(null);
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

  // ── Rich alert sound engine ──────────────────────────────────────────────
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
        // 3 rapid high-pitch aggressive bursts — demands immediate attention
        scheduleBeep(1100, now,        0.28, 0.65, "square");
        scheduleBeep(900,  now + 0.32, 0.28, 0.65, "square");
        scheduleBeep(1100, now + 0.64, 0.36, 0.70, "square");
      } else if (type === "target") {
        // 3 ascending celebratory tones — T1 / T2 hit
        scheduleBeep(660,  now,        0.30, 0.55, "sine");
        scheduleBeep(880,  now + 0.35, 0.30, 0.55, "sine");
        scheduleBeep(1100, now + 0.70, 0.50, 0.60, "sine");
      } else if (type === "warning") {
        // 2 moderate pulses — general alert / warning
        scheduleBeep(820, now,        0.35, 0.50, "triangle");
        scheduleBeep(820, now + 0.45, 0.35, 0.50, "triangle");
      }
    } catch {
      // ignore autoplay restrictions
    }
  };

  // ── Comprehensive alert monitor — all signal types ───────────────────────
  useEffect(() => {
    if (!Array.isArray(customPositions) || customPositions.length === 0) return;
    if (typeof window === "undefined" || document.hidden) return;
    if (!alertSoundEnabled) return;

    const urgentAlertSet = new Set(["EXIT_URGENT_TIME", "EXIT_URGENT_LOSS", "RISKY_PREMIUM", "EXIT_NOW_HIGH_LOSS", "EXIT_URGENT_NO_RECOVERY"]);
    const warningAlertSet = new Set(["EXIT_PREMIUM_DECAY", "APPROACHING_SL", "LOSS_WARNING"]);
    const targetStateSet = new Set(["WATCHING_T1", "WATCHING_T2", "CLOSED_WIN"]);

    // Urgent exit alerts
    const freshUrgent = customPositions.filter(
      (p) => urgentAlertSet.has(p.alert) && !urgentBuzzedRef.current.has(p.id)
    );
    if (freshUrgent.length > 0) {
      playAlertSound("urgent");
      freshUrgent.forEach((p) => urgentBuzzedRef.current.add(p.id));
    }

    // T1 / T2 target achievement
    const freshTargets = customPositions.filter(
      (p) => targetStateSet.has(p.signal_state) && !targetBuzzedRef.current.has(`${p.id}_${p.signal_state}`)
    );
    if (freshTargets.length > 0) {
      playAlertSound("target");
      freshTargets.forEach((p) => targetBuzzedRef.current.add(`${p.id}_${p.signal_state}`));
    }

    // Warning / general alerts
    const freshWarnings = customPositions.filter(
      (p) => warningAlertSet.has(p.alert) && !warningBuzzedRef.current.has(p.id)
    );
    if (freshWarnings.length > 0 && freshUrgent.length === 0) {
      // Don't play warning if urgent already played this cycle
      playAlertSound("warning");
      freshWarnings.forEach((p) => warningBuzzedRef.current.add(p.id));
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customPositions, alertSoundEnabled]);

  useEffect(() => {
    if (currentPage === "admin" && token) {
      checkKiteStatus();
      loadMacroEvents();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, token]);

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
    setMultibaggerProgress("");
    try {
      const response = await fetch(`${API}/multibagger/generate`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: "{}",
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }
      const data = await readNDJSONStream(response, (evt) => setMultibaggerProgress(evt.message || ""));
      if (data) {
        setMultibaggerData(data);
        syncCredits(data.credits_remaining);
      }
    } catch (error) {
      setMultibaggerError(error?.message || "Unable to generate multibagger list");
    } finally {
      setMultibaggerLoading(false);
      setMultibaggerProgress("");
    }
  };

  const loadSectorMomentum = async (forceRefresh = false) => {
    setSectorMomentumError("");
    setSectorMomentumLoading(true);
    try {
      const response = await axios.get(
        `${API}/sector-momentum${forceRefresh ? "?force_refresh=true" : ""}`,
        { headers: authHeaders }
      );
      setSectorMomentumData(response.data);
    } catch (error) {
      setSectorMomentumError(error?.response?.data?.detail || "Unable to load sector momentum data");
    } finally {
      setSectorMomentumLoading(false);
    }
  };

  const searchCustomMbStock = async (e) => {
    e.preventDefault();
    if (!customMbSymbol.trim()) return;
    setCustomMbError("");
    setCustomMbResult(null);
    setCustomMbLoading(true);
    try {
      const response = await axios.post(
        `${API}/multibagger/custom-search`,
        { symbol: customMbSymbol.trim().toUpperCase() },
        { headers: authHeaders }
      );
      setCustomMbResult(response.data);
    } catch (error) {
      setCustomMbError(error?.response?.data?.detail || `No data found for '${customMbSymbol}'. Check the NSE symbol.`);
    } finally {
      setCustomMbLoading(false);
    }
  };

  const generateFnoProjection = async (script = "") => {
    setFnoError("");
    setFnoLoading(true);
    setFnoProgress("");
    try {
      const payload = script ? { custom_script: script.trim().toUpperCase() } : {};
      const response = await fetch(`${API}/fno/generate`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }
      const data = await readNDJSONStream(response, (evt) => setFnoProgress(evt.message || ""));
      if (data) {
        setFnoData(data);
        syncCredits(data.credits_remaining);
      }
    } catch (error) {
      setFnoError(error?.message || "Unable to generate F&O projections");
    } finally {
      setFnoLoading(false);
      setFnoProgress("");
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
    const lotsNum = Number(customLots);
    if (!buyPriceNum || buyPriceNum <= 0) {
      setCustomPositionError("Enter a valid buy price.");
      return;
    }
    if (!lotsNum || lotsNum <= 0) {
      setCustomPositionError("Enter valid no. of lots (minimum 1).");
      return;
    }

    setCustomPositionLoading(true);
    try {
      const response = await axios.post(
        `${API}/fno/custom-position`,
        {
          script: customScript.trim().toUpperCase(),
          buy_price: buyPriceNum,
          quantity_lots: Math.floor(lotsNum),
        },
        { headers: authHeaders },
      );
      syncCredits(response.data.credits_remaining);
      setCustomBuyPrice("");
      setCustomLots("1");
      await loadCustomPositions();
    } catch (error) {
      setCustomPositionError(error?.response?.data?.detail || "Unable to create custom projection.");
    } finally {
      setCustomPositionLoading(false);
    }
  };

  const removeCustomProjection = async (positionId) => {
    setCustomPositions((prev) => prev.filter((position) => position.id !== positionId));
    try {
      await axios.delete(`${API}/fno/custom-position/${positionId}`, { headers: authHeaders });
      await loadCustomPositions();
    } catch (error) {
      await loadCustomPositions();
      setCustomPositionError(error?.response?.data?.detail || "Unable to remove custom projection.");
    }
  };

  const checkKiteStatus = async () => {
    if (!token) return;
    try {
      const response = await axios.get(`${API}/kite/status`, { headers: authHeaders });
      setKiteStatus(response.data);
    } catch (error) {
      setKiteStatus({ connected: false });
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
      if (!audioContextRef.current || audioContextRef.current.state === "closed") {
        audioContextRef.current = new AudioCtx();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      setAlertSoundEnabled(true);
      setShowSoundPrompt(false);
      setCustomPositionError("");

      // Play confirmation test tone (ascending 2-tone chime)
      setTimeout(() => playAlertSound("target"), 50);
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

  const loadMacroEvents = async () => {
    try {
      const response = await axios.get(`${API}/admin/macro-events`, { headers: authHeaders });
      setMacroEventsData(response.data);
    } catch (error) {
      // Non-critical: silently skip
    }
  };

  const toggleMacroEvent = async (key) => {
    const current = macroEventsData.active_events || [];
    const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
    setMacroEventsData((prev) => ({ ...prev, active_events: next }));
    setMacroEventsSaving(true);
    try {
      await axios.post(`${API}/admin/macro-events/update`, { events: next }, { headers: authHeaders });
    } catch (error) {
      // Revert on error
      setMacroEventsData((prev) => ({ ...prev, active_events: current }));
    } finally {
      setMacroEventsSaving(false);
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

  const deleteDomainMapping = async (domain) => {
    try {
      await axios.delete(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}`, { headers: authHeaders });
      setDomainDeleteConfirm(null);
      await loadAdminConfig();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to delete domain mapping");
    }
  };

  const mapDomain = async (domain) => {
    setDomainMapStatus((prev) => ({ ...prev, [domain]: { loading: true, result: null } }));
    try {
      const resp = await axios.post(`${API}/admin/domain-mappings/${encodeURIComponent(domain)}/map`, {}, { headers: authHeaders });
      setDomainMapStatus((prev) => ({ ...prev, [domain]: { loading: false, result: resp.data } }));
      await loadAdminConfig();
    } catch (error) {
      setDomainMapStatus((prev) => ({ ...prev, [domain]: { loading: false, result: { error: error?.response?.data?.detail || "Map failed" } } }));
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

  // ── CSV Seed Management Functions ──────────────────────────────────────
  const loadCsvSeeds = async () => {
    setCsvSeedLoading(true);
    setCsvSeedMsg("");
    try {
      const res = await axios.get(`${API}/admin/csv-seeds`, { headers: authHeaders });
      setCsvSeeds(res.data.seeds || []);
    } catch (err) {
      setCsvSeedMsg(err?.response?.data?.detail || "Unable to load CSV seeds");
    }
    setCsvSeedLoading(false);
  };
  const uploadCsvSeed = async (e) => {
    e.preventDefault();
    if (!csvUploadSymbol.trim()) { setCsvSeedMsg("Enter a symbol"); return; }
    const fileInput = e.target.querySelector('input[type="file"]');
    if (!fileInput?.files?.[0]) { setCsvSeedMsg("Select a CSV file"); return; }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    setCsvSeedLoading(true);
    try {
      const res = await axios.post(`${API}/admin/csv-seeds/${csvUploadSymbol.trim().toUpperCase()}`, formData, {
        headers: { ...authHeaders, "Content-Type": "multipart/form-data" },
      });
      setCsvSeedMsg(`Saved ${res.data.symbol}: ${res.data.rows} rows`);
      setCsvUploadSymbol("");
      fileInput.value = "";
      await loadCsvSeeds();
    } catch (err) {
      setCsvSeedMsg(err?.response?.data?.detail || "Upload failed");
    }
    setCsvSeedLoading(false);
  };
  const deleteCsvSeed = async (symbol) => {
    try {
      await axios.delete(`${API}/admin/csv-seeds/${symbol}`, { headers: authHeaders });
      setCsvSeedMsg(`Deleted ${symbol}`);
      await loadCsvSeeds();
    } catch (err) {
      setCsvSeedMsg(err?.response?.data?.detail || "Delete failed");
    }
  };
  // ── End CSV Seed Functions ─────────────────────────────────────────────

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
          <Button
            type="button"
            onClick={() => { setCurrentPage("sectors"); if (!sectorMomentumData) loadSectorMomentum(); }}
            className={currentPage === "sectors" ? "bg-cyan-500 text-slate-900 hover:bg-cyan-400" : "border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"}
            data-testid="nav-sectors"
          >
            <GaugeCircle size={16} /> Sectors
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

              <Card
                className="cursor-pointer border-cyan-500/30 bg-slate-900/70 transition-colors hover:border-cyan-400"
                onClick={() => { setCurrentPage("sectors"); if (!sectorMomentumData) loadSectorMomentum(); }}
                data-testid="home-module-sectors"
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-cyan-300">
                    <GaugeCircle size={18} /> Sector Momentum
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-300">
                    Live momentum scores for 15 NSE sectors — 1W/1M/3M returns, RSI and trend direction.
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
                  {multibaggerLoading ? (multibaggerProgress || "Finding...") : "Find Multibagger (-2)"}
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
                {/* Custom stock search */}
                <form onSubmit={searchCustomMbStock} className="flex flex-col gap-2 sm:flex-row" data-testid="mb-custom-search-form">
                  <Input
                    value={customMbSymbol}
                    onChange={(e) => setCustomMbSymbol(e.target.value.toUpperCase())}
                    placeholder="Search any NSE symbol (e.g. RELIANCE, INFY)"
                    className="font-mono border-slate-700 bg-slate-900 text-slate-100"
                    data-testid="mb-custom-search-input"
                  />
                  <Button
                    type="submit"
                    disabled={customMbLoading || !customMbSymbol.trim()}
                    className="border border-cyan-700 bg-cyan-900/30 text-cyan-300 hover:bg-cyan-800/50"
                    data-testid="mb-custom-search-btn"
                  >
                    <RefreshCw size={14} className={customMbLoading ? "animate-spin mr-1" : "mr-1"} />
                    {customMbLoading ? "Analyzing..." : "Analyze Stock"}
                  </Button>
                </form>
                {customMbError ? <p className="text-sm text-rose-400" data-testid="mb-custom-search-error">{customMbError}</p> : null}
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
                        {filteredMultibaggers.map((row) => (
                          <TableBody key={`group-${row.symbol}`} className="multibagger-group cursor-pointer">
                            <TableRow data-testid={`multibagger-target-row-${row.symbol.toLowerCase()}`}>
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
                            <TableRow data-testid={`multibagger-roi-row-${row.symbol.toLowerCase()}`}>
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
                            {(row.roe != null || row.roce != null || row.piotroski_score != null || row.beneish_m_score != null || row.eps_growth_pct != null) ? (
                              <TableRow data-testid={`multibagger-fundamentals-row-${row.symbol.toLowerCase()}`}>
                                <TableCell colSpan={12} className="py-1 bg-slate-900/40">
                                  <div className="flex flex-wrap gap-2 text-xs">
                                    {row.roe != null && (
                                      <span className={`rounded px-2 py-0.5 font-semibold ${row.roe >= 20 ? 'bg-emerald-900/50 text-emerald-300' : row.roe >= 12 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                        ROE: {row.roe}%
                                      </span>
                                    )}
                                    {row.roce != null && (
                                      <span className={`rounded px-2 py-0.5 font-semibold ${row.roce >= 15 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-yellow-900/50 text-yellow-300'}`}>
                                        ROCE: {row.roce}%
                                      </span>
                                    )}
                                    {row.piotroski_score != null && (
                                      <span className={`rounded px-2 py-0.5 font-semibold ${row.piotroski_score >= 7 ? 'bg-emerald-900/50 text-emerald-300' : row.piotroski_score >= 5 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                        Piotroski: {row.piotroski_score}/9
                                      </span>
                                    )}
                                    {row.beneish_m_score != null && (
                                      <span className={`rounded px-2 py-0.5 font-semibold ${row.beneish_m_score <= -2.22 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                        Beneish M: {row.beneish_m_score} {row.beneish_m_score > -2.22 ? '⚠' : '✓'}
                                      </span>
                                    )}
                                    {row.eps_growth_pct != null && (
                                      <span className={`rounded px-2 py-0.5 font-semibold ${row.eps_growth_pct > 0 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                        EPS Growth: {row.eps_growth_pct > 0 ? '+' : ''}{row.eps_growth_pct}%
                                      </span>
                                    )}
                                    {row.debt_to_equity != null && (
                                      <span className={`rounded px-2 py-0.5 font-semibold ${row.debt_to_equity < 0.5 ? 'bg-emerald-900/50 text-emerald-300' : row.debt_to_equity < 1.5 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                        D/E: {Number(row.debt_to_equity).toFixed(2)}
                                      </span>
                                    )}
                                  </div>
                                </TableCell>
                              </TableRow>
                            ) : null}
                            <TableRow data-testid={`multibagger-thesis-row-${row.symbol.toLowerCase()}`}>
                              <TableCell colSpan={12} className="py-2 text-xs text-slate-300 leading-relaxed border-b border-slate-800/60">
                                <span className="font-semibold text-cyan-400 mr-2">Thesis:</span>
                                {(row.thesis || "No thesis available").split(" | ").map((part, i) => (
                                  <span key={i} className="inline-block mr-3 mb-1">
                                    {i > 0 && <span className="text-slate-600 mr-3">|</span>}
                                    {part}
                                  </span>
                                ))}
                              </TableCell>
                            </TableRow>
                            {row.vol_bands ? (
                              <TableRow data-testid={`multibagger-bands-toggle-row-${row.symbol.toLowerCase()}`}>
                                <TableCell colSpan={12} className="py-1 bg-slate-900/20">
                                  <button
                                    className="text-xs text-cyan-400 hover:text-cyan-300 underline"
                                    onClick={() => setExpandedMbBands(prev => ({...prev, [row.symbol]: !prev[row.symbol]}))}
                                    data-testid={`multibagger-bands-toggle-${row.symbol.toLowerCase()}`}
                                  >
                                    {expandedMbBands[row.symbol] ? "Hide" : "Show"} Price Bands (Conservative / Expected / Optimistic)
                                  </button>
                                  {expandedMbBands[row.symbol] ? (
                                    <div className="mt-2 overflow-auto" data-testid={`multibagger-bands-table-${row.symbol.toLowerCase()}`}>
                                      <table className="w-full text-xs border-collapse">
                                        <thead>
                                          <tr className="text-slate-400 border-b border-slate-700">
                                            <th className="text-left py-1 pr-3">Horizon</th>
                                            <th className="text-right py-1 pr-3">Conservative</th>
                                            <th className="text-right py-1 pr-3">Expected Upside</th>
                                            <th className="text-right py-1 pr-3">Expected Downside</th>
                                            <th className="text-right py-1 pr-3">Optimistic</th>
                                            <th className="text-right py-1 pr-3">HV%</th>
                                            <th className="text-right py-1">Signal</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {["1W","1M","3M","6M","9M","1Y"].map(h => {
                                            const b = row.vol_bands[h];
                                            if (!b) return null;
                                            const ltp = row.ltp || 0;
                                            return (
                                              <tr key={h} className="border-b border-slate-800/40">
                                                <td className="py-1 pr-3 font-mono font-semibold text-slate-300">{h}</td>
                                                <td className="text-right pr-3 text-yellow-300">+{b.conservative_high_pct?.toFixed(1)}%</td>
                                                <td className="text-right pr-3 text-emerald-300">+{b.upside_pct?.toFixed(1)}% (₹{formatNumber(ltp * (1 + b.upside_pct/100))})</td>
                                                <td className="text-right pr-3 text-rose-300">{b.downside_pct?.toFixed(1)}% (₹{formatNumber(ltp * (1 + b.downside_pct/100))})</td>
                                                <td className="text-right pr-3 text-cyan-300">+{b.optimistic_high_pct?.toFixed(1)}%</td>
                                                <td className="text-right pr-3 text-slate-400">{b.hist_vol_pct?.toFixed(1)}%</td>
                                                <td className="text-right">
                                                  <span className={`rounded px-1 ${b.flag === 'GREEN' ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>{b.flag}</span>
                                                </td>
                                              </tr>
                                            );
                                          })}
                                        </tbody>
                                      </table>
                                      <p className="mt-1 text-slate-500">Based on {row.vol_bands["1M"]?.hist_vol_pct?.toFixed(1)}% annualized historical volatility. Conservative = 1σ, Expected = 1.5σ, Optimistic = 2σ.</p>
                                    </div>
                                  ) : null}
                                </TableCell>
                              </TableRow>
                            ) : null}
                          </TableBody>
                        ))}
                    </Table>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {/* Custom stock search result */}
            {customMbResult ? (
              <Card className="result-card border-cyan-800/50 bg-slate-950/70" data-testid="mb-custom-result-card">
                <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
                  <CardTitle className="text-white text-base">
                    Custom Analysis: <span className="font-mono text-cyan-300">{customMbResult.symbol}</span>
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge className={`border ${scoreBadge(customMbResult.is_potential_multibagger)}`}>
                      Score: {customMbResult.multibagger_score}
                    </Badge>
                    <Badge className={`border ${scoreBadge(customMbResult.is_potential_multibagger)}`}>
                      {customMbResult.is_potential_multibagger ? "POTENTIAL MULTIBAGGER" : "WATCHLIST"}
                    </Badge>
                    <button
                      onClick={() => setCustomMbResult(null)}
                      className="text-slate-400 hover:text-white"
                      data-testid="mb-custom-result-close"
                    >
                      <X size={16} />
                    </button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-800" data-testid="mb-custom-result-table-wrapper">
                    <Table>
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
                      <TableBody className="multibagger-group cursor-pointer" data-testid="mb-custom-result-group">
                        <TableRow>
                          <TableCell className="font-mono text-cyan-300">{customMbResult.company_name}</TableCell>
                          <TableCell>{customMbResult.sector}</TableCell>
                          <TableCell className="font-mono">{formatNumber(customMbResult.current_rsi_level)}</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.gtt_buy_price)}</TableCell>
                          <TableCell className="text-slate-400">Targeted Upside Price</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.targeted_upside_price?.["1W"])}</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.targeted_upside_price?.["1M"])}</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.targeted_upside_price?.["3M"])}</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.targeted_upside_price?.["6M"])}</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.targeted_upside_price?.["9M"])}</TableCell>
                          <TableCell className="font-mono">₹{formatNumber(customMbResult.targeted_upside_price?.["1Y"])}</TableCell>
                          <TableCell>
                            <Badge className={`border ${scoreBadge(customMbResult.is_potential_multibagger)}`}>
                              {customMbResult.multibagger_score}
                            </Badge>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="font-mono text-slate-400">{customMbResult.symbol}</TableCell>
                          <TableCell className="text-slate-500">Tier: {customMbResult.tier_pass_count}/8</TableCell>
                          <TableCell className="text-slate-500">LTP: ₹{formatNumber(customMbResult.ltp)}</TableCell>
                          <TableCell className="text-slate-500">PE: {formatNumber(customMbResult.pe_ratio)}</TableCell>
                          <TableCell className="text-slate-400">% Profit</TableCell>
                          <TableCell className="font-mono text-emerald-300">{formatNumber(customMbResult.targeted_upside_profit_pct?.["1W"])}%</TableCell>
                          <TableCell className="font-mono text-emerald-300">{formatNumber(customMbResult.targeted_upside_profit_pct?.["1M"])}%</TableCell>
                          <TableCell className="font-mono text-emerald-300">{formatNumber(customMbResult.targeted_upside_profit_pct?.["3M"])}%</TableCell>
                          <TableCell className="font-mono text-emerald-300">{formatNumber(customMbResult.targeted_upside_profit_pct?.["6M"])}%</TableCell>
                          <TableCell className="font-mono text-emerald-300">{formatNumber(customMbResult.targeted_upside_profit_pct?.["9M"])}%</TableCell>
                          <TableCell className="font-mono text-emerald-300">{formatNumber(customMbResult.targeted_upside_profit_pct?.["1Y"])}%</TableCell>
                          <TableCell>
                            <Badge className={`border ${scoreBadge(customMbResult.is_potential_multibagger)}`}>
                              {customMbResult.is_potential_multibagger ? "POTENTIAL" : "WATCH"}
                            </Badge>
                          </TableCell>
                        </TableRow>
                        {(customMbResult.roe != null || customMbResult.roce != null || customMbResult.piotroski_score != null) ? (
                          <TableRow>
                            <TableCell colSpan={12} className="py-1 bg-slate-900/40">
                              <div className="flex flex-wrap gap-2 text-xs">
                                {customMbResult.roe != null && (
                                  <span className={`rounded px-2 py-0.5 font-semibold ${customMbResult.roe >= 20 ? 'bg-emerald-900/50 text-emerald-300' : customMbResult.roe >= 12 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                    ROE: {customMbResult.roe}%
                                  </span>
                                )}
                                {customMbResult.roce != null && (
                                  <span className={`rounded px-2 py-0.5 font-semibold ${customMbResult.roce >= 15 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-yellow-900/50 text-yellow-300'}`}>
                                    ROCE: {customMbResult.roce}%
                                  </span>
                                )}
                                {customMbResult.piotroski_score != null && (
                                  <span className={`rounded px-2 py-0.5 font-semibold ${customMbResult.piotroski_score >= 7 ? 'bg-emerald-900/50 text-emerald-300' : customMbResult.piotroski_score >= 5 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                    Piotroski: {customMbResult.piotroski_score}/9
                                  </span>
                                )}
                                {customMbResult.debt_to_equity != null && (
                                  <span className={`rounded px-2 py-0.5 font-semibold ${customMbResult.debt_to_equity < 0.5 ? 'bg-emerald-900/50 text-emerald-300' : customMbResult.debt_to_equity < 1.5 ? 'bg-yellow-900/50 text-yellow-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                    D/E: {Number(customMbResult.debt_to_equity).toFixed(2)}
                                  </span>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        ) : null}
                        <TableRow>
                          <TableCell colSpan={12} className="py-2 text-xs text-slate-300 leading-relaxed">
                            <span className="font-semibold text-cyan-400 mr-2">Thesis:</span>
                            {(customMbResult.thesis || "No thesis available").split(" | ").map((part, i) => (
                              <span key={i} className="inline-block mr-3 mb-1">
                                {i > 0 && <span className="text-slate-600 mr-3">|</span>}
                                {part}
                              </span>
                            ))}
                          </TableCell>
                        </TableRow>
                        {customMbResult.vol_bands ? (
                          <TableRow>
                            <TableCell colSpan={12} className="py-1 bg-slate-900/20">
                              <p className="text-xs font-semibold text-cyan-400 mb-1">Price Bands (Conservative / Expected / Optimistic):</p>
                              <div className="overflow-auto">
                                <table className="w-full text-xs border-collapse">
                                  <thead>
                                    <tr className="text-slate-400 border-b border-slate-700">
                                      <th className="text-left py-1 pr-3">Horizon</th>
                                      <th className="text-right pr-3">Conservative</th>
                                      <th className="text-right pr-3">Expected Upside</th>
                                      <th className="text-right pr-3">Expected Downside</th>
                                      <th className="text-right pr-3">Optimistic</th>
                                      <th className="text-right">Signal</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {["1W","1M","3M","6M","9M","1Y"].map(h => {
                                      const b = customMbResult.vol_bands[h];
                                      if (!b) return null;
                                      const ltp = customMbResult.ltp || 0;
                                      return (
                                        <tr key={h} className="border-b border-slate-800/40">
                                          <td className="py-1 pr-3 font-mono font-semibold text-slate-300">{h}</td>
                                          <td className="text-right pr-3 text-yellow-300">+{b.conservative_high_pct?.toFixed(1)}%</td>
                                          <td className="text-right pr-3 text-emerald-300">+{b.upside_pct?.toFixed(1)}% (₹{formatNumber(ltp*(1+b.upside_pct/100))})</td>
                                          <td className="text-right pr-3 text-rose-300">{b.downside_pct?.toFixed(1)}% (₹{formatNumber(ltp*(1+b.downside_pct/100))})</td>
                                          <td className="text-right pr-3 text-cyan-300">+{b.optimistic_high_pct?.toFixed(1)}%</td>
                                          <td className="text-right"><span className={`rounded px-1 ${b.flag==='GREEN'?'bg-emerald-900/50 text-emerald-300':'bg-rose-900/50 text-rose-300'}`}>{b.flag}</span></td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </section>
        ) : null}

        {currentPage === "sectors" ? (
          <section className="space-y-6" data-testid="sectors-page">
            <Card className="result-card border-slate-800 bg-slate-950/70">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">Sector Momentum Dashboard</CardTitle>
                <Button
                  type="button"
                  onClick={() => loadSectorMomentum(true)}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="sector-momentum-refresh-button"
                  disabled={sectorMomentumLoading}
                >
                  <RefreshCw size={16} className={sectorMomentumLoading ? "animate-spin" : ""} />
                  {sectorMomentumLoading ? "Loading..." : "Refresh Data"}
                </Button>
              </CardHeader>
              <CardContent>
                {sectorMomentumError ? (
                  <p className="text-sm text-rose-400" data-testid="sector-momentum-error">{sectorMomentumError}</p>
                ) : null}
                {!sectorMomentumData && !sectorMomentumLoading ? (
                  <div className="flex flex-col items-center gap-3 py-8 text-slate-400" data-testid="sector-momentum-empty">
                    <GaugeCircle size={40} className="opacity-40" />
                    <p className="text-sm">Click <strong>Refresh Data</strong> to load live sector momentum.</p>
                    <Button
                      type="button"
                      onClick={() => loadSectorMomentum()}
                      className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                      data-testid="sector-momentum-load-button"
                    >
                      Load Sector Momentum
                    </Button>
                  </div>
                ) : sectorMomentumLoading ? (
                  <div className="flex items-center gap-2 py-8 text-slate-400" data-testid="sector-momentum-loading">
                    <RefreshCw size={20} className="animate-spin" />
                    <span>Fetching live data for 15 sectors... (may take ~30s on first load)</span>
                  </div>
                ) : null}

                {sectorMomentumData ? (
                  <>
                    {/* Summary Strip */}
                    <div className="mb-4 flex flex-wrap gap-3 text-sm" data-testid="sector-momentum-summary">
                      <span className="rounded bg-emerald-900/40 px-2 py-1 text-emerald-300 font-semibold">
                        Bullish: {sectorMomentumData.summary?.bullish_sectors ?? 0}
                      </span>
                      <span className="rounded bg-rose-900/40 px-2 py-1 text-rose-300 font-semibold">
                        Bearish: {sectorMomentumData.summary?.bearish_sectors ?? 0}
                      </span>
                      <span className="rounded bg-slate-700 px-2 py-1 text-slate-300 font-semibold">
                        Neutral: {sectorMomentumData.summary?.neutral_sectors ?? 0}
                      </span>
                      <span className="rounded bg-cyan-900/40 px-2 py-1 text-cyan-300 font-semibold">
                        Market: {sectorMomentumData.summary?.market_breadth ?? "—"}
                      </span>
                      <span className="rounded bg-slate-800 px-2 py-1 text-slate-400 text-xs font-mono">
                        Avg Score: {sectorMomentumData.summary?.avg_momentum_score ?? "—"}
                      </span>
                      {sectorMomentumData.from_cache ? (
                        <span className="rounded bg-slate-800 px-2 py-1 text-slate-500 text-xs">cached</span>
                      ) : null}
                      <span className="rounded bg-slate-800 px-2 py-1 text-slate-500 text-xs font-mono">
                        {sectorMomentumData.refreshed_at ? new Date(sectorMomentumData.refreshed_at).toLocaleTimeString("en-IN") : ""}
                      </span>
                    </div>

                    {/* Sector Grid */}
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="sector-momentum-grid">
                      {(sectorMomentumData.sectors || []).map((s) => (
                        <div
                          key={s.sector}
                          className="rounded-lg border border-slate-700 bg-slate-900/60 p-3"
                          data-testid={`sector-card-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}
                        >
                          <div className="mb-2 flex items-center justify-between">
                            <span className="font-semibold text-slate-100 text-sm">{s.sector}</span>
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-xs font-bold rounded px-2 py-0.5 ${
                                  s.direction === "STRONG_BULL" ? "bg-emerald-900/60 text-emerald-300" :
                                  s.direction === "BULL" ? "bg-green-900/60 text-green-400" :
                                  s.direction === "NEUTRAL" ? "bg-yellow-900/60 text-yellow-300" :
                                  s.direction === "BEAR" ? "bg-orange-900/60 text-orange-400" :
                                  "bg-rose-900/60 text-rose-300"
                                }`}
                                data-testid={`sector-direction-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}
                              >
                                {s.direction_label}
                              </span>
                              <span
                                className="text-xs font-mono font-bold text-white bg-slate-700 rounded px-2 py-0.5"
                                data-testid={`sector-score-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}
                              >
                                {s.momentum_score}
                              </span>
                            </div>
                          </div>

                          {/* Momentum Score Bar */}
                          <div className="mb-2 h-1.5 w-full rounded-full bg-slate-700">
                            <div
                              className={`h-1.5 rounded-full transition-all ${
                                s.direction === "STRONG_BULL" ? "bg-emerald-400" :
                                s.direction === "BULL" ? "bg-green-400" :
                                s.direction === "NEUTRAL" ? "bg-yellow-400" :
                                s.direction === "BEAR" ? "bg-orange-400" :
                                "bg-rose-500"
                              }`}
                              style={{ width: `${s.momentum_score}%` }}
                            />
                          </div>

                          {/* Return Metrics */}
                          <div className="grid grid-cols-3 gap-1 text-xs mb-2">
                            <div className="text-center">
                              <p className="text-slate-500">1W</p>
                              <p className={`font-mono font-semibold ${(s.return_1w ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}
                                data-testid={`sector-return-1w-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                                {s.return_1w != null ? `${s.return_1w >= 0 ? '+' : ''}${s.return_1w.toFixed(1)}%` : "—"}
                              </p>
                            </div>
                            <div className="text-center">
                              <p className="text-slate-500">1M</p>
                              <p className={`font-mono font-semibold ${(s.return_1m ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}
                                data-testid={`sector-return-1m-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                                {s.return_1m != null ? `${s.return_1m >= 0 ? '+' : ''}${s.return_1m.toFixed(1)}%` : "—"}
                              </p>
                            </div>
                            <div className="text-center">
                              <p className="text-slate-500">3M</p>
                              <p className={`font-mono font-semibold ${(s.return_3m ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}
                                data-testid={`sector-return-3m-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                                {s.return_3m != null ? `${s.return_3m >= 0 ? '+' : ''}${s.return_3m.toFixed(1)}%` : "—"}
                              </p>
                            </div>
                          </div>

                          {/* RSI + ADX row */}
                          <div className="flex flex-wrap gap-2 text-xs">
                            {s.rsi != null && (
                              <span className={`rounded px-1.5 py-0.5 ${s.rsi > 65 ? 'bg-orange-900/50 text-orange-300' : s.rsi < 35 ? 'bg-rose-900/50 text-rose-300' : 'bg-slate-800 text-slate-400'}`}
                                data-testid={`sector-rsi-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                                RSI {s.rsi.toFixed(0)}
                              </span>
                            )}
                            {s.adx != null && (
                              <span className={`rounded px-1.5 py-0.5 ${s.adx > 25 ? 'bg-cyan-900/50 text-cyan-300' : 'bg-slate-800 text-slate-400'}`}
                                data-testid={`sector-adx-${s.sector.toLowerCase().replace(/[^a-z]/g, '-')}`}>
                                ADX {s.adx.toFixed(0)} ({s.trend_strength})
                              </span>
                            )}
                            <span className="rounded px-1.5 py-0.5 bg-slate-800 text-slate-500">
                              {s.stocks_tracked} stocks
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : null}
              </CardContent>
            </Card>
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
                  {fnoLoading ? (fnoProgress || "Generating...") : "Generate F&O Projections (-2)"}
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
                  <Input
                    value={customLots}
                    onChange={(event) => setCustomLots(event.target.value)}
                    type="number"
                    min="1"
                    step="1"
                    placeholder="No. of Lots"
                    className="w-full border-slate-700 bg-slate-900 text-slate-100 lg:w-36"
                    data-testid="fno-custom-lots-input"
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
                    Alerts on: Urgent exits, T1/T2 target hits, and warnings — loud multi-tone sound.
                  </span>
                </div>
                {showSoundPrompt ? (
                  <div className="rounded-md border border-cyan-500/40 bg-cyan-500/10 p-3 text-xs text-cyan-100" data-testid="sound-permission-note">
                    <p className="mb-2 font-semibold">Enable alert sound before custom projection?</p>
                    <p className="mb-2">Loud multi-tone alerts for: T1/T2 target hits, urgent exit conditions, SL warnings, and high-loss signals.</p>
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
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3" data-testid="custom-position-list">
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
                          className={`result-card result-hover custom-position-yellow-card rounded-lg border p-3 ${urgent ? "urgent-alert-card" : "border-amber-500"}`}
                          data-testid={`custom-position-card-${position.id}`}
                        >
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <p className="font-mono text-slate-900" data-testid={`custom-position-script-${position.id}`}>{position.script}</p>
                            <Badge className="border border-emerald-600 bg-emerald-500/20 text-emerald-200" data-testid={`custom-position-status-${position.id}`}>
                              {position.status}
                            </Badge>
                          </div>
                          <div className="grid grid-cols-1 gap-1 text-xs md:grid-cols-2">
                            <p>Buy Price: <span className="font-mono">₹{formatNumber(position.buy_price)}</span></p>
                            <p>Lots / Units: <span className="font-mono">{position.quantity_lots} / {position.units}</span></p>
                            <p>
                              Live LTP: <span className="font-mono text-sm font-extrabold text-slate-900" data-testid={`custom-position-live-ltp-${position.id}`}>₹{formatNumber(position.latest_option_ltp)}</span>
                            </p>
                            <p>
                              LTP vs Buy: <span className={`font-mono font-semibold ${ltpDeltaClass}`} data-testid={`custom-position-buy-diff-${position.id}`}>{formatSignedInr(position.buy_to_ltp_diff)}</span>
                            </p>
                            {position.sold_price !== null && position.sold_price !== undefined ? (
                              <p className="md:col-span-2 custom-position-pnl-box" data-testid={`custom-position-realized-pnl-${position.id}`}>
                                Sold @ <span className="font-mono">₹{formatNumber(position.sold_price)}</span> | Realized P&L: <span className={`ml-1 font-mono font-extrabold ${Number(position.realized_pnl || 0) >= 0 ? "text-emerald-100" : "text-rose-100"}`}>{formatSignedInr(position.realized_pnl)}</span>
                              </p>
                            ) : (
                              <p className="md:col-span-2 custom-position-pnl-box" data-testid={`custom-position-pnl-box-${position.id}`}>
                                P/L (Lot Size Based):
                                <span className={`ml-1 font-mono font-extrabold ${Number(position.floating_pnl_amount || 0) >= 0 ? "text-emerald-100" : "text-rose-100"}`}>
                                  {formatSignedInr(position.floating_pnl_amount)} ({position.floating_pnl_pct !== null && position.floating_pnl_pct !== undefined ? `${position.floating_pnl_pct > 0 ? "+" : ""}${formatNumber(position.floating_pnl_pct)}%` : "-"})
                                </span>
                              </p>
                            )}
                            <p>Target1 / Target2: <span className="font-mono">₹{formatNumber(position.target1)} / ₹{formatNumber(position.target2)}</span></p>
                            <p>
                              To T1 / T2: <span className="font-mono" data-testid={`custom-position-target-diff-${position.id}`}>₹{formatNumber(position.ltp_to_t1_diff)} / ₹{formatNumber(position.ltp_to_t2_diff)}</span>
                            </p>
                            <p>Expiry in: <span className="font-mono">{position.minutes_to_expiry} min</span></p>
                            <p>Recovery Potential: <span className="font-mono" data-testid={`custom-position-recovery-${position.id}`}>{position.recovery_potential !== null && position.recovery_potential !== undefined ? `${formatNumber(position.recovery_potential * 100)}%` : "-"}</span></p>
                            <p>
                              T1 Status: <span className="inline-flex items-center gap-1 font-semibold" data-testid={`custom-position-t1-status-${position.id}`}>{position.target1_achieved ? <><CheckCircle2 size={14} className="text-blue-600" /> Achieved</> : "Pending"}</span>
                            </p>
                            <p>
                              T2 Status: <span className="inline-flex items-center gap-1 font-semibold" data-testid={`custom-position-t2-status-${position.id}`}>{position.target2_achieved ? <><CheckCircle2 size={14} className="text-blue-600" /> Achieved</> : "Pending"}</span>
                            </p>
                            <p className="md:col-span-2">Exit Plan: <span className="font-mono">{position.revised_exit_plan}</span></p>
                          </div>
                          {/* BEST EXIT for custom positions */}
                          {exitPrice && position.status !== "SOLD" ? (
                            <div className="mt-2">
                              {position.best_exit_date_str?.includes("Today") || position.remaining_trading_days === 0 ? (
                                <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse" data-testid={`expiry-today-badge-${position.id}`}>
                                  EXPIRY TODAY — Exit Before 3:30 PM
                                </span>
                              ) : position.remaining_trading_days <= 2 && position.remaining_trading_days > 0 ? (
                                <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
                                  ⚠ Near Expiry ({position.remaining_trading_days} trading days left)
                                </span>
                              ) : null}
                              <p className="text-sm font-semibold text-green-400" data-testid={`custom-position-best-exit-${position.id}`}>
                                ⭐ BEST EXIT: T+{position.best_exit_days ?? "?"} Trading Days{position.best_exit_date_str ? ` (${position.best_exit_date_str})` : ""} @ ₹{formatNumber(exitPrice)}
                              </p>
                            </div>
                          ) : null}
                          <div className="mt-3 flex items-center justify-end gap-2">
                            {position.can_sell ? (
                              <Button
                                type="button"
                                onClick={() => openSellDialog(position)}
                                className="h-8 border border-emerald-500 bg-emerald-500/10 px-3 text-emerald-200 hover:bg-emerald-500/20"
                                data-testid={`custom-position-sold-button-${position.id}`}
                              >
                                Sold
                              </Button>
                            ) : null}
                            <Button
                              type="button"
                              onClick={() => removeCustomProjection(position.id)}
                              className="h-8 border border-rose-600 bg-rose-500/10 px-3 text-rose-800 hover:bg-rose-500/20"
                              data-testid={`custom-position-close-${position.id}`}
                            >
                              <X size={14} />
                            </Button>
                          </div>
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
                  <div className="flex items-center justify-between gap-4 flex-wrap">
                    <p className="text-xs text-slate-400" data-testid="fno-refreshed-at">
                      Refreshed at: {formatTime(fnoData.analysis_refreshed_at)} | Charged: {fnoData.cost_charged}
                    </p>
                    {/* Export Results Button */}
                    <div className="relative">
                      <Button
                        data-testid="fno-export-btn"
                        variant="outline"
                        size="sm"
                        className="border-cyan-700 bg-cyan-900/30 text-cyan-300 hover:bg-cyan-800/50 gap-1.5"
                        onClick={() => setExportMenuOpen((v) => !v)}
                      >
                        <Download className="h-3.5 w-3.5" />
                        Export Results
                      </Button>
                      {exportMenuOpen && (
                        <div
                          className="absolute right-0 top-9 z-50 flex flex-col gap-0.5 rounded-lg border border-cyan-800 bg-slate-900 p-1 shadow-xl"
                          data-testid="fno-export-menu"
                        >
                          {[
                            { label: "Export as CSV", ext: "csv", icon: "📄", testid: "export-csv" },
                            { label: "Export as XLS", ext: "xls", icon: "📊", testid: "export-xls" },
                            { label: "Export as PDF", ext: "pdf", icon: "📑", testid: "export-pdf" },
                            { label: "Export as Word", ext: "doc", icon: "📝", testid: "export-doc" },
                            { label: "Export as JPG", ext: "jpg", icon: "🖼", testid: "export-jpg" },
                          ].map(({ label, ext, icon, testid }) => (
                            <button
                              key={ext}
                              data-testid={testid}
                              className="flex items-center gap-2 rounded px-4 py-2 text-sm text-slate-200 hover:bg-cyan-900/50 hover:text-white transition-colors whitespace-nowrap"
                              onClick={() => {
                                setExportMenuOpen(false);
                                if (ext === "csv") exportFnoAsCSV(fnoData);
                                else if (ext === "xls") exportFnoAsXLS(fnoData);
                                else if (ext === "pdf") exportFnoAsPDF(fnoData);
                                else if (ext === "doc") exportFnoAsWord(fnoData);
                                else exportFnoAsJPG(exportTableRef);
                              }}
                            >
                              <span>{icon}</span>
                              {label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
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
                                {pane.assured_signals.slice(0, 5).map((signal, idx) => (
                                  <div key={signal.script} className="result-hover rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                                    <div className="mb-1 flex items-center justify-between">
                                      <span className="font-mono text-cyan-200">{signal.script}</span>
                                      <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                                    </div>
                                    {renderLiveInfoBox(signal, `assured-${pane.index_name.toLowerCase()}-${idx}`)}
                                    <p>Expiry: {formatExpiryDate(signal.expiry)}{signal.remaining_trading_days > 0 ? ` · ${signal.remaining_trading_days} trading days left` : ""}</p>
                                    {signal.expiry_today_badge ? (
                                      <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse">
                                        EXPIRY TODAY — Exit Before 3:30 PM
                                      </span>
                                    ) : signal.near_expiry_badge ? (
                                      <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
                                        ⚠ Near Expiry
                                      </span>
                                    ) : null}
                                    <p>Entry/SL/T1/T2: ₹{formatNumber(signal.entry_price)} / ₹{formatNumber(signal.stop_loss)} / ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                                    <p>Confluence: {signal.confluence_score >= 80 ? "⭐ " : ""}{signal.confluence_score} ({signal.signal_quality})</p>
                                    {signal.best_exit_price && (
                                      <p className="text-green-400 font-semibold text-sm">
                                        ⭐ BEST EXIT: T+{signal.best_exit_days} Trading Days{signal.best_exit_date_str ? ` (${signal.best_exit_date_str})` : ""} @ ₹{formatNumber(signal.best_exit_price)}
                                      </p>
                                    )}
                                    {signal.budget_entry_alert && signal.best_budget_entry && (
                                      <div className="mt-1 p-1.5 rounded border border-amber-600/50 bg-amber-950/30" data-testid={`budget-entry-alert-${signal.script?.toLowerCase()}-assured`}>
                                        <span className="font-bold text-amber-300 text-xs">⏳ Wait for Budget Entry</span>
                                        <span className="text-amber-100 text-xs ml-1">Pullback to ₹{formatNumber(signal.best_budget_entry)} — do not enter at ₹{formatNumber(signal.entry_price)}</span>
                                      </div>
                                    )}
                                    {(signal.underlying_day_change_pct !== null || signal.underlying_bias_score !== null) && (
                                      <div className="mt-1 flex flex-wrap gap-2">
                                        {signal.underlying_day_change_pct !== null && (
                                          <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.underlying_day_change_pct >= 0 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                            Day Change: {signal.underlying_day_change_pct?.toFixed(2)}%
                                          </span>
                                        )}
                                        {signal.underlying_bias_score !== null && (
                                          <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.underlying_bias_score >= 0 ? 'bg-blue-900/50 text-blue-300' : 'bg-orange-900/50 text-orange-300'}`}>
                                            Bias: {signal.underlying_bias_score?.toFixed(2)}
                                          </span>
                                        )}
                                      </div>
                                    )}
                                    {(signal.iv_rank_52w !== null || signal.atm_iv !== null) && (
                                      <div className="mt-1 flex flex-wrap gap-2">
                                        {signal.atm_iv !== null && (
                                          <span className="rounded px-1.5 py-0.5 text-xs font-semibold bg-violet-900/50 text-violet-300" data-testid={`atm-iv-${signal.script?.toLowerCase()}`}>
                                            ATM IV: {signal.atm_iv?.toFixed(1)}%
                                          </span>
                                        )}
                                        {signal.iv_rank_52w !== null && (
                                          <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.iv_rank_52w >= 70 ? 'bg-red-900/50 text-red-300' : signal.iv_rank_52w <= 30 ? 'bg-green-900/50 text-green-300' : 'bg-zinc-800/50 text-zinc-300'}`} data-testid={`iv-rank-52w-${signal.script?.toLowerCase()}`}>
                                            IV Rank 52W: {signal.iv_rank_52w?.toFixed(1)}%
                                          </span>
                                        )}
                                      </div>
                                    )}
                                    {String(signal.strategy || "").toUpperCase().includes("CAUTION") ? (
                                      <p className="font-semibold text-amber-200">⚠ Caution: Probable setup only. Use strict stop-loss and position sizing.</p>
                                    ) : null}
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
                                {pane.watchlist_signals.map((signal, idx) => (
                                  <div key={`${signal.script}-watch`} className="result-hover rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs">
                                    <div className="mb-1 flex items-center justify-between">
                                      <span className="font-mono text-emerald-200">{signal.script}</span>
                                      <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                                    </div>
                                    {renderLiveInfoBox(signal, `watch-${pane.index_name.toLowerCase()}-${idx}`)}
                                    <p>Expiry: {formatExpiryDate(signal.expiry)}{signal.remaining_trading_days > 0 ? ` · ${signal.remaining_trading_days} trading days left` : ""}</p>
                                    {signal.expiry_today_badge ? (
                                      <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse">
                                        EXPIRY TODAY — Exit Before 3:30 PM
                                      </span>
                                    ) : signal.near_expiry_badge ? (
                                      <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
                                        ⚠ Near Expiry
                                      </span>
                                    ) : null}
                                    <p>Entry/SL/T1/T2: ₹{formatNumber(signal.entry_price)} / ₹{formatNumber(signal.stop_loss)} / ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                                    <p>Confluence: {signal.confluence_score >= 80 ? "⭐ " : ""}{signal.confluence_score} ({signal.signal_quality})</p>
                                    {signal.budget_entry_alert && signal.best_budget_entry && (
                                      <div className="mt-1 p-1.5 rounded border border-amber-600/50 bg-amber-950/30" data-testid={`budget-entry-alert-${signal.script?.toLowerCase()}-watch`}>
                                        <span className="font-bold text-amber-300 text-xs">⏳ Wait for Budget Entry</span>
                                        <span className="text-amber-100 text-xs ml-1">Pullback to ₹{formatNumber(signal.best_budget_entry)} — do not enter at ₹{formatNumber(signal.entry_price)}</span>
                                      </div>
                                    )}
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
                        fnoData.stock_signals.map((signal, idx) => (
                          <div key={signal.script} className="result-hover rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs" data-testid={`stock-fno-signal-${signal.script.toLowerCase()}`}>
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <p className="font-mono text-cyan-200">{signal.script}</p>
                              <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                            </div>
                            {renderLiveInfoBox(signal, `stock-${idx}`)}
                            <p data-testid={`stock-fno-signal-expiry-${signal.script.toLowerCase()}`}>Expiry: {formatExpiryDate(signal.expiry)}{signal.remaining_trading_days > 0 ? ` · ${signal.remaining_trading_days} trading days left` : ""} (monthly stock contract)</p>
                            {signal.expiry_today_badge ? (
                              <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse">
                                EXPIRY TODAY — Exit Before 3:30 PM
                              </span>
                            ) : signal.near_expiry_badge ? (
                              <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
                                ⚠ Near Expiry
                              </span>
                            ) : null}
                            <p>Entry: ₹{formatNumber(signal.entry_price)}</p>
                            <p>SL: ₹{formatNumber(signal.stop_loss)}</p>
                            <p>T1/T2: ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                            <p>Confidence: {signal.confluence_score >= 80 ? "⭐ " : ""}{signal.confluence_score}</p>
                            {signal.best_exit_price && (
                              <p className="text-green-400 font-semibold text-sm">
                                ⭐ BEST EXIT: T+{signal.best_exit_days} Trading Days{signal.best_exit_date_str ? ` (${signal.best_exit_date_str})` : ""} @ ₹{formatNumber(signal.best_exit_price)}
                              </p>
                            )}
                            {signal.budget_entry_alert && signal.best_budget_entry && (
                              <div className="mt-1 p-1.5 rounded border border-amber-600/50 bg-amber-950/30" data-testid={`budget-entry-alert-${signal.script?.toLowerCase()}-stock`}>
                                <span className="font-bold text-amber-300 text-xs">⏳ Wait for Budget Entry</span>
                                <span className="text-amber-100 text-xs ml-1">Pullback to ₹{formatNumber(signal.best_budget_entry)} — do not enter at ₹{formatNumber(signal.entry_price)}</span>
                              </div>
                            )}
                            {(signal.underlying_day_change_pct !== null || signal.underlying_bias_score !== null) && (
                              <div className="mt-1 flex flex-wrap gap-2">
                                {signal.underlying_day_change_pct !== null && (
                                  <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.underlying_day_change_pct >= 0 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                    Day Change: {signal.underlying_day_change_pct?.toFixed(2)}%
                                  </span>
                                )}
                                {signal.underlying_bias_score !== null && (
                                  <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${signal.underlying_bias_score >= 0 ? 'bg-blue-900/50 text-blue-300' : 'bg-orange-900/50 text-orange-300'}`}>
                                    Bias: {signal.underlying_bias_score?.toFixed(2)}
                                  </span>
                                )}
                              </div>
                            )}
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
                          fnoData.top_trades.map((trade, idx) => (
                            <div key={trade.script} className="result-hover rounded-md border border-slate-800 bg-slate-900/70 p-3 text-xs" data-testid={`top4-trade-${trade.script.toLowerCase()}`}>
                              <div className="mb-2 flex items-center justify-between">
                                <p className="font-mono text-cyan-200">{trade.script}</p>
                                <Badge className={`border ${qualityBadge(trade.signal_quality)}`}>{trade.signal_quality}</Badge>
                              </div>
                              {renderLiveInfoBox(trade, `top4-${idx}`)}
                              <p>Entry: ₹{formatNumber(trade.entry_price)}</p>
                              <p>SL: ₹{formatNumber(trade.stop_loss)}</p>
                              <p>T1/T2: ₹{formatNumber(trade.target1)} / ₹{formatNumber(trade.target2)}</p>
                              <p>Confidence: {trade.confluence_score >= 80 ? "⭐ " : ""}{trade.confluence_score} | {trade.direction}</p>
                              {trade.expiry_today_badge ? (
                                <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-red-600/30 text-red-300 border border-red-500/70 mb-1 animate-pulse">
                                  EXPIRY TODAY — Exit Before 3:30 PM
                                </span>
                              ) : trade.near_expiry_badge ? (
                                <span className="inline-block rounded px-1.5 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 mb-1">
                                  ⚠ Near Expiry ({trade.remaining_trading_days} days)
                                </span>
                              ) : null}
                              {trade.best_exit_price && (
                                <p className="text-green-400 font-semibold text-sm">
                                  ⭐ BEST EXIT: T+{trade.best_exit_days} Trading Days{trade.best_exit_date_str ? ` (${trade.best_exit_date_str})` : ""} @ ₹{formatNumber(trade.best_exit_price)}
                                </p>
                              )}
                              {trade.budget_entry_alert && trade.best_budget_entry && (
                                <div className="mt-1 p-1.5 rounded border border-amber-600/50 bg-amber-950/30" data-testid={`budget-entry-alert-${trade.script?.toLowerCase()}-top4`}>
                                  <span className="font-bold text-amber-300 text-xs">⏳ Wait for Budget Entry</span>
                                  <span className="text-amber-100 text-xs ml-1">Pullback to ₹{formatNumber(trade.best_budget_entry)} — do not enter at ₹{formatNumber(trade.entry_price)}</span>
                                </div>
                              )}
                              {(trade.underlying_day_change_pct !== null || trade.underlying_bias_score !== null) && (
                                <div className="mt-1 flex flex-wrap gap-2">
                                  {trade.underlying_day_change_pct !== null && (
                                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${trade.underlying_day_change_pct >= 0 ? 'bg-emerald-900/50 text-emerald-300' : 'bg-rose-900/50 text-rose-300'}`}>
                                      Day Change: {trade.underlying_day_change_pct?.toFixed(2)}%
                                    </span>
                                  )}
                                  {trade.underlying_bias_score !== null && (
                                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${trade.underlying_bias_score >= 0 ? 'bg-blue-900/50 text-blue-300' : 'bg-orange-900/50 text-orange-300'}`}>
                                      Bias: {trade.underlying_bias_score?.toFixed(2)}
                                    </span>
                                  )}
                                </div>
                              )}
                              {(trade.iv_rank_52w !== null || trade.atm_iv !== null) && (
                                <div className="mt-1 flex flex-wrap gap-2">
                                  {trade.atm_iv !== null && (
                                    <span className="rounded px-1.5 py-0.5 text-xs font-semibold bg-violet-900/50 text-violet-300" data-testid={`atm-iv-top4-${trade.script?.toLowerCase()}`}>
                                      ATM IV: {trade.atm_iv?.toFixed(1)}%
                                    </span>
                                  )}
                                  {trade.iv_rank_52w !== null && (
                                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${trade.iv_rank_52w >= 70 ? 'bg-red-900/50 text-red-300' : trade.iv_rank_52w <= 30 ? 'bg-green-900/50 text-green-300' : 'bg-zinc-800/50 text-zinc-300'}`} data-testid={`iv-rank-52w-top4-${trade.script?.toLowerCase()}`}>
                                      IV Rank 52W: {trade.iv_rank_52w?.toFixed(1)}%
                                    </span>
                                  )}
                                </div>
                              )}
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
                          {renderLiveInfoBox(fnoData.custom_signal, "custom-script-result")}
                          <p>Direction: {fnoData.custom_signal.direction}</p>
                          <p>Entry/SL/T1/T2: ₹{formatNumber(fnoData.custom_signal.entry_price)} / ₹{formatNumber(fnoData.custom_signal.stop_loss)} / ₹{formatNumber(fnoData.custom_signal.target1)} / ₹{formatNumber(fnoData.custom_signal.target2)}</p>
                          <p>Confluence: {fnoData.custom_signal.confluence_score >= 80 ? "⭐ " : ""}{fnoData.custom_signal.confluence_score}</p>
                        </CardContent>
                      </Card>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}

            {/* Hidden Export Table for JPG capture */}
            {fnoData && (
              <div
                ref={exportTableRef}
                style={{
                  position: "absolute",
                  left: "-9999px",
                  top: 0,
                  width: "1100px",
                  background: "#ffffff",
                  padding: "24px",
                  fontFamily: "Arial, sans-serif",
                  fontSize: "13px",
                  color: "#1a1a1a",
                }}
              >
                <h2 style={{ fontSize: "16px", fontWeight: "bold", marginBottom: "8px", color: "#FFFFFF", background: "#1E3A5F", padding: "8px 12px", borderRadius: "4px" }}>
                  Stock Options — Correct Lot Sizes के साथ
                </h2>
                <table style={{ width: "100%", borderCollapse: "collapse", color: "#1A1A1A" }}>
                  <thead>
                    <tr style={{ background: "#1E3A5F" }}>
                      {["Script", "Bias", "Lot", "Entry ₹", "SL", "T1", "T2", "Investment (₹)", "T1%", "T1 Profit ₹", "T2%", "T2 Profit ₹", "Conf", "Bias Point"].map((h) => (
                        <th key={h} style={{ border: "1px solid #d1d5db", padding: "6px 8px", textAlign: "center", fontWeight: "600", fontSize: "12px", color: "#FFFFFF" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {collectAllFnoSignals(fnoData).map((sig, i) => {
                      const row = buildExportRow(sig);
                      return (
                        <tr key={sig.script} style={{ background: i % 2 === 0 ? "#ffffff" : "#f0f4f8", color: "#1A1A1A" }}>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", fontWeight: "500", color: "#1A1A1A" }}>{row["Script"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "center", color: row["Bias"] === "BULLISH" ? "#059669" : "#dc2626", fontWeight: "600" }}>{row["Bias"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>{row["Lot"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>₹{row["Entry ₹"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#dc2626" }}>{row["SL"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>{row["T1"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>{row["T2"]}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#1A1A1A" }}>₹{Number(row["Investment (₹)"]).toLocaleString("en-IN")}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T1%"]).toFixed(2)}%</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>₹{Number(row["T1 Profit ₹"]).toLocaleString("en-IN")}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>{Number(row["T2%"]).toFixed(2)}%</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: "#059669" }}>₹{Number(row["T2 Profit ₹"]).toLocaleString("en-IN")}</td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "center", fontWeight: "600", color: row["Conf"] >= 80 ? "#D97706" : "#1A1A1A" }}>
                            {row["Conf"] >= 80 ? "⭐ " : ""}{row["Conf"]}
                          </td>
                          <td style={{ border: "1px solid #e5e7eb", padding: "5px 8px", textAlign: "right", color: row["Bias Point"] >= 0 ? "#2563EB" : "#EA580C" }}>{Number(row["Bias Point"]).toFixed(2)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p style={{ marginTop: "12px", fontSize: "11px", color: "#6b7280" }}>
                  Note: सभी lot sizes NSE verified हैं (March 2026 – dhan.co) — Investment = Entry Price × Lot Size (1 lot premium cost) | Generated: {new Date().toLocaleString("en-IN")}
                </p>
              </div>
            )}
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

            {/* Failed symbols warning — non-blocking */}
            {portfolioData?.failed_symbols?.length > 0 && (
              <div className="flex flex-wrap gap-2 rounded-md border border-yellow-800 bg-yellow-900/20 p-3" data-testid="portfolio-failed-symbols-banner">
                <span className="text-xs font-semibold text-yellow-400">Live data temporarily unavailable:</span>
                {portfolioData.failed_symbols.map((sym) => (
                  <span key={sym} className="rounded-full bg-yellow-900/50 px-2 py-0.5 text-xs font-mono text-yellow-300 border border-yellow-700" data-testid={`portfolio-failed-badge-${sym.toLowerCase()}`}>
                    {sym}
                  </span>
                ))}
                <span className="text-xs text-yellow-500">(remaining symbols analysed normally)</span>
              </div>
            )}

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
                              <TableHead>Max Price (Upside)</TableHead>
                              <TableHead>Max Low (Downside)</TableHead>
                              <TableHead>Amount (+/-)</TableHead>
                              <TableHead>Percent (+/-)</TableHead>
                              <TableHead>Signal</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {Object.entries(stock.expected_signals || {}).map(([horizon, values]) => (
                              <TableRow key={`${stock.symbol}-${horizon}`} className="hover:bg-white/5">
                                <TableCell>{horizon}</TableCell>
                                <TableCell className="font-mono text-emerald-300">₹{formatNumber(values.max_expected_price)}</TableCell>
                                <TableCell className="font-mono text-rose-300">
                                  {values.min_expected_price != null ? `₹${formatNumber(values.min_expected_price)}` : "—"}
                                </TableCell>
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

                  <div className="space-y-3" data-testid="admin-domain-list">
                    {(adminConfig?.domain_mappings || []).length === 0 && (
                      <p className="text-xs text-slate-500">No domain mappings yet. Add one above.</p>
                    )}
                    {(adminConfig?.domain_mappings || []).map((row) => {
                      const mapInfo = domainMapStatus[row.domain];
                      const statusColor = row.status === "ACTIVE" ? "bg-emerald-600"
                        : row.status === "PENDING_DNS" || row.status === "NGINX_CONFIG_GENERATED" ? "bg-yellow-600"
                        : row.status === "FAILED" ? "bg-rose-600"
                        : "bg-slate-600";
                      return (
                        <div key={row.domain} className="rounded-lg border border-slate-700 bg-slate-900/80 p-3 space-y-2" data-testid={`admin-domain-card-${row.domain}`}>
                          {/* Header row */}
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="space-y-0.5 text-xs">
                              <p className="font-mono font-semibold text-cyan-300">{row.domain}</p>
                              <p className="text-slate-400">A Record: {row.resolved_target_ip || row.target_record || "—"}</p>
                            </div>
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold text-white ${statusColor}`}>
                              {row.status}
                            </span>
                          </div>
                          {/* Action buttons */}
                          <div className="flex flex-wrap gap-2">
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => mapDomain(row.domain)}
                              disabled={mapInfo?.loading}
                              className="h-7 bg-cyan-700 px-3 text-xs text-white hover:bg-cyan-600"
                              data-testid={`admin-domain-map-${row.domain}`}
                            >
                              {mapInfo?.loading ? "Mapping…" : "MAP"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => updateDomainStatus(row.domain, "ACTIVE")}
                              className="h-7 bg-emerald-700 px-3 text-xs text-white hover:bg-emerald-600"
                              data-testid={`admin-domain-active-${row.domain}`}
                            >
                              Mark Active
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => setExpandedDnsInstructions((prev) => ({ ...prev, [row.domain]: !prev[row.domain] }))}
                              className="h-7 bg-slate-700 px-3 text-xs text-white hover:bg-slate-600"
                              data-testid={`admin-domain-dns-toggle-${row.domain}`}
                            >
                              {expandedDnsInstructions[row.domain] ? "Hide DNS" : "DNS Instructions"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => setDomainDeleteConfirm(row.domain)}
                              className="h-7 bg-rose-700 px-3 text-xs text-white hover:bg-rose-600"
                              data-testid={`admin-domain-delete-${row.domain}`}
                            >
                              Delete
                            </Button>
                          </div>
                          {/* DNS Instructions (expandable) */}
                          {expandedDnsInstructions[row.domain] && (
                            <div className="rounded-md border border-slate-700 bg-slate-950 p-3 text-xs text-slate-300 space-y-1" data-testid={`admin-domain-dns-${row.domain}`}>
                              <p className="font-semibold text-cyan-300 mb-1">DNS Setup Instructions</p>
                              <p>1. Open your domain registrar / DNS provider</p>
                              <p>2. Add an <strong>A Record</strong>: Host = <code className="text-yellow-300">{row.host_label || "@"}</code>, Value = <code className="text-yellow-300">{row.resolved_target_ip || row.target_record || "[server IP]"}</code>, TTL = 300</p>
                              <p>3. Delete any conflicting A record for the same host label</p>
                              <p>4. Wait 5–30 minutes for propagation</p>
                              <p>5. After DNS resolves, click <strong>MAP</strong> above to configure the server proxy</p>
                            </div>
                          )}
                          {/* Map result */}
                          {mapInfo?.result && (
                            <div className={`rounded-md p-2 text-xs ${mapInfo.result.error ? "bg-rose-900/40 text-rose-300" : "bg-emerald-900/40 text-emerald-300"}`} data-testid={`admin-domain-map-result-${row.domain}`}>
                              {mapInfo.result.error ? `Map error: ${mapInfo.result.error}` : `Mapped (${mapInfo.result.nginx_status}) — DNS must point to server IP`}
                            </div>
                          )}
                          {/* Delete confirm dialog */}
                          {domainDeleteConfirm === row.domain && (
                            <div className="rounded-md border border-rose-700 bg-rose-950/60 p-3 text-xs space-y-2" data-testid={`admin-domain-delete-confirm-${row.domain}`}>
                              <p className="text-rose-300 font-semibold">Confirm delete domain mapping: <span className="font-mono">{row.domain}</span>?</p>
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => deleteDomainMapping(row.domain)} className="h-7 bg-rose-600 px-3 text-xs text-white hover:bg-rose-500" data-testid="admin-domain-delete-confirm-yes">Yes, Delete</Button>
                                <Button size="sm" onClick={() => setDomainDeleteConfirm(null)} className="h-7 bg-slate-700 px-3 text-xs text-white hover:bg-slate-600" data-testid="admin-domain-delete-confirm-no">Cancel</Button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {isOwner && (
              <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="admin-macro-events-card">
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                  <div>
                    <CardTitle className="text-white">Active Macro Events</CardTitle>
                    <p className="mt-1 text-xs text-slate-400">
                      Toggle events to influence sector macro bias in F&amp;O signals and Multibagger analysis. Changes apply instantly.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {macroEventsSaving && (
                      <span className="text-xs text-cyan-400" data-testid="macro-events-saving">Saving…</span>
                    )}
                    <Button
                      type="button"
                      onClick={loadMacroEvents}
                      className="bg-slate-800 text-slate-100 hover:bg-slate-700 h-8 px-3 text-xs"
                      data-testid="admin-macro-events-refresh"
                    >
                      Refresh
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {macroEventsData.active_events.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-1.5" data-testid="macro-events-active-summary">
                      <span className="text-xs text-slate-500">Active:</span>
                      {macroEventsData.active_events.map((key) => (
                        <span key={key} className="rounded-full bg-cyan-900/60 px-2 py-0.5 text-xs font-medium text-cyan-300 border border-cyan-700/50">
                          {key}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="macro-events-grid">
                    {(macroEventsData.all_events || []).map((event) => {
                      const isActive = macroEventsData.active_events.includes(event.key);
                      const intensityColor = {
                        CRITICAL: "text-rose-400 border-rose-700/60 bg-rose-950/40",
                        HIGH: "text-orange-400 border-orange-700/60 bg-orange-950/40",
                        MEDIUM: "text-yellow-400 border-yellow-700/60 bg-yellow-950/40",
                        LOW: "text-slate-400 border-slate-700/60 bg-slate-900/40",
                      }[event.intensity] || "text-slate-400 border-slate-700/60 bg-slate-900/40";

                      return (
                        <button
                          key={event.key}
                          type="button"
                          data-testid={`macro-event-toggle-${event.key}`}
                          onClick={() => toggleMacroEvent(event.key)}
                          className={`flex items-start justify-between rounded-lg border p-2.5 text-left transition-all ${
                            isActive
                              ? "border-cyan-500 bg-cyan-900/30 ring-1 ring-cyan-500/40"
                              : "border-slate-700 bg-slate-900/60 hover:border-slate-600"
                          }`}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className={`text-xs font-semibold ${isActive ? "text-cyan-300" : "text-slate-300"}`}>
                                {event.key}
                              </span>
                              <span className={`rounded px-1 py-px text-[10px] font-medium border ${intensityColor}`}>
                                {event.intensity}
                              </span>
                            </div>
                            {event.description && (
                              <p className="mt-0.5 text-[11px] text-slate-500 leading-tight line-clamp-2">{event.description}</p>
                            )}
                            {event.beneficiaries?.length > 0 && (
                              <p className="mt-0.5 text-[10px] text-emerald-500/80">
                                + {event.beneficiaries.slice(0, 3).join(", ")}
                              </p>
                            )}
                          </div>
                          <div className={`ml-2 mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 transition-colors ${
                            isActive ? "border-cyan-400 bg-cyan-400" : "border-slate-600 bg-transparent"
                          }`} />
                        </button>
                      );
                    })}
                  </div>
                  {macroEventsData.all_events.length === 0 && (
                    <p className="text-xs text-slate-500" data-testid="macro-events-empty">No events loaded. Click Refresh to load.</p>
                  )}
                </CardContent>
              </Card>
            )}

            {isOwner && (
              <Card className="result-card border-slate-800 bg-slate-950/70">
                <CardHeader>
                  <CardTitle className="text-white">Kite Connect Integration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-4">
                    <div className="space-y-2">
                      <p className="text-sm font-semibold text-slate-200">Connection Status</p>
                      <div className="flex items-center gap-2">
                        {kiteStatus?.connected ? (
                          <>
                            <span className="inline-block h-3 w-3 rounded-full bg-green-500"></span>
                            <span className="text-sm text-green-400">✅ Connected</span>
                            <span className="text-xs text-slate-400">| User: {kiteStatus.user_id}</span>
                          </>
                        ) : (
                          <>
                            <span className="inline-block h-3 w-3 rounded-full bg-red-500"></span>
                            <span className="text-sm text-red-400">❌ Disconnected</span>
                          </>
                        )}
                      </div>
                      {kiteStatus?.date && (
                        <p className="text-xs text-slate-500">Last authenticated: {kiteStatus.date}</p>
                      )}
                    </div>
                    <Button
                      type="button"
                      onClick={async () => {
                        try {
                          const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/kite/auth-url`, {
                            headers: { Authorization: `Bearer ${token}` },
                          });
                          const data = await res.json();
                          if (data.auth_url) {
                            window.open(data.auth_url, '_blank');
                            setTimeout(() => checkKiteStatus(), 3000);
                          }
                        } catch (err) {
                          console.error('Kite auth error:', err);
                        }
                      }}
                      className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                    >
                      Connect Kite
                    </Button>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                    <p className="text-xs font-semibold text-slate-300 mb-2">OAuth URL:</p>
                    <p className="text-xs text-cyan-400 break-all font-mono">
                      https://kite.zerodha.com/connect/login?v=3&api_key=wgbgees3zbjpn254
                    </p>
                    <p className="text-xs text-slate-500 mt-2">
                      Note: Kite authentication expires daily. Re-authenticate each trading day for live data.
                    </p>
                  </div>
                  <Button
                    type="button"
                    onClick={checkKiteStatus}
                    className="bg-slate-800 text-slate-100 hover:bg-slate-700"
                  >
                    Refresh Status
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* CSV Seed Management (OHLCV Data) */}
            <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="csv-seed-card">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">OHLCV CSV Seed Management</CardTitle>
                <Button
                  type="button"
                  onClick={loadCsvSeeds}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="csv-seed-refresh-btn"
                >
                  Refresh Seeds
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200" data-testid="csv-seed-guide">
                  <p className="font-semibold mb-1">Admin Guide: CSV Seed Files</p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    <li>Upload verified CSV files with columns: <code className="bg-slate-800 px-1 rounded">date,open,high,low,close,volume</code></li>
                    <li>Files are named by symbol (e.g., NIFTY.csv, RELIANCE.csv)</li>
                    <li>Used ONLY when Kite Connect is unavailable (offline fallback)</li>
                    <li>Data must be manually verified before upload — no auto-scraping</li>
                    <li>Primary source is always Kite Connect Historical Data API</li>
                  </ul>
                </div>
                <form onSubmit={uploadCsvSeed} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="csv-seed-upload-form">
                  <Input
                    value={csvUploadSymbol}
                    onChange={(e) => setCsvUploadSymbol(e.target.value)}
                    placeholder="Symbol (e.g., NIFTY)"
                    className="border-slate-700 bg-slate-900 text-slate-100"
                    data-testid="csv-seed-symbol-input"
                  />
                  <input
                    type="file"
                    accept=".csv"
                    className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-cyan-500/20 file:px-2 file:py-1 file:text-xs file:text-cyan-300"
                    data-testid="csv-seed-file-input"
                  />
                  <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" disabled={csvSeedLoading} data-testid="csv-seed-upload-btn">
                    Upload CSV
                  </Button>
                </form>
                {csvSeedMsg ? <p className="text-sm text-cyan-300" data-testid="csv-seed-msg">{csvSeedMsg}</p> : null}
                {csvSeedLoading ? (
                  <p className="text-sm text-slate-400">Loading...</p>
                ) : csvSeeds.length > 0 ? (
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-800">
                    <Table data-testid="csv-seed-table">
                      <TableHeader>
                        <TableRow className="border-slate-800 hover:bg-slate-900/50">
                          <TableHead className="text-slate-400">Symbol</TableHead>
                          <TableHead className="text-slate-400">File</TableHead>
                          <TableHead className="text-right text-slate-400">Rows</TableHead>
                          <TableHead className="text-right text-slate-400">Size (KB)</TableHead>
                          <TableHead className="text-right text-slate-400">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {csvSeeds.map((seed) => (
                          <TableRow key={seed.symbol} className="border-slate-800 hover:bg-slate-900/50">
                            <TableCell className="font-medium text-white">{seed.symbol}</TableCell>
                            <TableCell className="text-slate-300">{seed.file}</TableCell>
                            <TableCell className="text-right text-slate-300">{seed.rows}</TableCell>
                            <TableCell className="text-right text-slate-300">{seed.size_kb}</TableCell>
                            <TableCell className="text-right">
                              <Button
                                type="button"
                                onClick={() => deleteCsvSeed(seed.symbol)}
                                className="bg-rose-500/20 text-rose-300 hover:bg-rose-500/40 text-xs h-7 px-2"
                                data-testid={`csv-seed-delete-${seed.symbol}`}
                              >
                                Delete
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500" data-testid="csv-seed-empty">No CSV seeds uploaded. Backtests will use Kite Connect data only.</p>
                )}
              </CardContent>
            </Card>
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
