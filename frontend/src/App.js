import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Activity,
  BarChart3,
  KeyRound,
  LogOut,
  RefreshCw,
  Shield,
  Sparkles,
  TrendingUp,
  Users,
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

const formatTime = (isoValue) => {
  if (!isoValue) return "-";
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

const getDirectionClass = (direction) => {
  if (direction === "BULLISH") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (direction === "BEARISH") return "bg-rose-50 text-rose-700 border-rose-200";
  return "bg-slate-100 text-slate-700 border-slate-300";
};

const getQualityClass = (quality) => {
  if (quality === "HIGH") return "bg-emerald-600 text-white border-emerald-700";
  if (quality === "MEDIUM") return "bg-amber-500 text-white border-amber-600";
  return "bg-slate-200 text-slate-700 border-slate-300";
};

const getScoreClass = (isPotential, score) => {
  if (isPotential) return "bg-cyan-500 text-slate-900 border-cyan-600";
  if (score >= 70) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (score >= 50) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-slate-100 text-slate-700 border-slate-300";
};

const defaultAdminForm = { password: "", initial_credits: 0 };

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("stock_auth_token") || "");
  const [user, setUser] = useState(null);
  const [authPassword, setAuthPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");

  const [activeTab, setActiveTab] = useState("multibagger");

  const [minScore, setMinScore] = useState(60);
  const [multibaggerData, setMultibaggerData] = useState(null);
  const [multibaggerLoading, setMultibaggerLoading] = useState(false);
  const [multibaggerError, setMultibaggerError] = useState("");

  const [fnoData, setFnoData] = useState(null);
  const [fnoLoading, setFnoLoading] = useState(false);
  const [fnoError, setFnoError] = useState("");
  const [script, setScript] = useState("NIFTY10MAR26500PE");

  const [adminUsers, setAdminUsers] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminError, setAdminError] = useState("");
  const [adminForm, setAdminForm] = useState(defaultAdminForm);
  const [creditEditMap, setCreditEditMap] = useState({});

  const authHeaders = useMemo(() => (token ? { Authorization: `Bearer ${token}` } : {}), [token]);

  const loadMe = async (activeToken) => {
    const response = await axios.get(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${activeToken}` },
    });
    setUser(response.data);
    return response.data;
  };

  useEffect(() => {
    const bootstrap = async () => {
      if (!token) return;
      try {
        await loadMe(token);
      } catch {
        localStorage.removeItem("stock_auth_token");
        setToken("");
        setUser(null);
      }
    };
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onAccess = async (event) => {
    event.preventDefault();
    setAuthError("");
    if (!/^[A-Za-z0-9]{6,}$/.test(authPassword)) {
      setAuthError("Password must be at least 6 characters and only letters/numbers.");
      return;
    }
    setAuthLoading(true);
    try {
      const response = await axios.post(`${API}/auth/access`, { password: authPassword });
      const newToken = response.data.token;
      localStorage.setItem("stock_auth_token", newToken);
      setToken(newToken);
      setUser({
        role: response.data.role,
        credits: response.data.credits,
        user_key: response.data.user_key,
      });
      setAuthPassword("");
    } catch (error) {
      setAuthError(error?.response?.data?.detail || "Unable to authenticate.");
    } finally {
      setAuthLoading(false);
    }
  };

  const onLogout = async () => {
    try {
      if (token) {
        await axios.post(`${API}/auth/logout`, {}, { headers: authHeaders });
      }
    } catch {
      // ignore
    } finally {
      localStorage.removeItem("stock_auth_token");
      setToken("");
      setUser(null);
      setMultibaggerData(null);
      setFnoData(null);
      setAdminUsers([]);
    }
  };

  const syncCredits = (credits) => {
    setUser((prev) => (prev ? { ...prev, credits } : prev));
  };

  const generateMultibaggers = async () => {
    setMultibaggerLoading(true);
    setMultibaggerError("");
    try {
      const response = await axios.post(`${API}/multibagger/generate`, {}, { headers: authHeaders });
      setMultibaggerData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setMultibaggerError(error?.response?.data?.detail || "Unable to generate multibaggers.");
    } finally {
      setMultibaggerLoading(false);
    }
  };

  const generateFno = async (customScript = null) => {
    setFnoLoading(true);
    setFnoError("");
    try {
      const payload = customScript ? { custom_script: customScript.trim().toUpperCase() } : {};
      const response = await axios.post(`${API}/fno/generate`, payload, { headers: authHeaders });
      setFnoData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setFnoError(error?.response?.data?.detail || "Unable to generate F&O signals.");
    } finally {
      setFnoLoading(false);
    }
  };

  const loadAdminUsers = async () => {
    setAdminLoading(true);
    setAdminError("");
    try {
      const response = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      setAdminUsers(response.data || []);
      const map = {};
      (response.data || []).forEach((item) => {
        map[item.user_key] = item.credits;
      });
      setCreditEditMap(map);
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to load users.");
    } finally {
      setAdminLoading(false);
    }
  };

  const createUserByAdmin = async (event) => {
    event.preventDefault();
    setAdminError("");
    try {
      await axios.post(`${API}/admin/users`, adminForm, { headers: authHeaders });
      setAdminForm(defaultAdminForm);
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to create user.");
    }
  };

  const updateCredits = async (userKey) => {
    try {
      await axios.patch(
        `${API}/admin/users/${userKey}/credits`,
        { credits: Number(creditEditMap[userKey] || 0) },
        { headers: authHeaders },
      );
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to update credits.");
    }
  };

  const deleteUser = async (userKey) => {
    try {
      await axios.delete(`${API}/admin/users/${userKey}`, { headers: authHeaders });
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to delete user.");
    }
  };

  const filteredCandidates = useMemo(() => {
    if (!multibaggerData?.candidates) return [];
    return multibaggerData.candidates.filter((row) => row.multibagger_score >= minScore);
  }, [multibaggerData, minScore]);

  const bestTrades = useMemo(() => {
    if (!fnoData?.top_trades) return [];
    return fnoData.top_trades.slice(0, 4);
  }, [fnoData]);

  if (!token || !user) {
    return (
      <main className="min-h-screen bg-black text-white" data-testid="landing-page">
        <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-4 py-10 text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-cyan-500/50 bg-cyan-500/10 px-4 py-1 text-xs text-cyan-300" data-testid="landing-chip">
            <Sparkles size={14} />
            SMART AI STOCK RESEARCH
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl lg:text-6xl" data-testid="landing-title">
            Password Protected Research Dashboard
          </h1>
          <p className="mt-4 max-w-3xl text-sm text-slate-300 sm:text-base" data-testid="landing-subtitle">
            Personal testing and educational usage only. Enter your access password to use credit-based Multibagger and F&O live analysis.
          </p>

          <form onSubmit={onAccess} className="mt-8 w-full max-w-md space-y-3" data-testid="landing-access-form">
            <Input
              type="password"
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
              placeholder="Enter password (min 6, letters/numbers)"
              className="h-11 border-slate-700 bg-slate-950 text-white placeholder:text-slate-400"
              data-testid="landing-password-input"
            />
            <Button
              type="submit"
              className="h-11 w-full bg-cyan-500 text-slate-900 hover:bg-cyan-400"
              data-testid="landing-access-button"
            >
              <KeyRound size={16} />
              {authLoading ? "Verifying..." : "Access Dashboard"}
            </Button>
            {authError ? (
              <p className="text-sm text-rose-400" data-testid="landing-auth-error">{authError}</p>
            ) : null}
          </form>

          <div className="mt-10 w-full max-w-4xl rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-left" data-testid="landing-disclaimer-block">
            <p className="text-sm font-semibold text-cyan-300">Personal Testing & SEBI Educational Disclaimer</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              This product is strictly for educational research, simulation, and personal testing. It does not provide investment advice,
              stock recommendation, or guaranteed returns. Please consult a SEBI-registered investment advisor before making real trades.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900" data-testid="dashboard-page">
      <div className="architect-grid-overlay" />
      <div className="relative mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-8 space-y-4" data-testid="dashboard-header">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600" data-testid="header-chip">
              <Activity size={14} />
              Live Market Dashboard
            </div>
            <Button
              type="button"
              onClick={onLogout}
              className="border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
              data-testid="logout-button"
            >
              <LogOut size={16} />
              Logout
            </Button>
          </div>

          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl" data-testid="dashboard-title">
            AI Stock Research – Multibagger & F&O
          </h1>
          <p className="text-sm text-slate-500 sm:text-base" data-testid="dashboard-subtitle">
            Lightweight, button-driven live analysis. Nothing generates until you click a generate button.
          </p>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="summary-cards">
            <Card data-testid="summary-user-card">
              <CardContent className="pt-6">
                <p className="text-sm text-slate-500">Session User</p>
                <p className="mt-2 font-mono text-lg">{user.user_key.slice(0, 8)}...</p>
                <p className="mt-1 text-xs text-slate-500">Role: {user.role.toUpperCase()}</p>
              </CardContent>
            </Card>
            <Card data-testid="summary-credit-card">
              <CardContent className="pt-6">
                <p className="text-sm text-slate-500">Available Credits</p>
                <p className="mt-2 font-mono text-3xl font-semibold">{user.credits}</p>
                <p className="mt-1 text-xs text-slate-500">Multibagger = 1 | F&O = 2</p>
              </CardContent>
            </Card>
            <Card data-testid="summary-disclaimer-card">
              <CardContent className="pt-6">
                <p className="text-sm text-slate-500">Usage Scope</p>
                <p className="mt-2 text-sm font-medium text-slate-800">Personal Testing + Educational</p>
                <p className="mt-1 text-xs text-slate-500">Not investment advice</p>
              </CardContent>
            </Card>
          </div>
        </header>

        <section className="mb-6 flex flex-wrap gap-3" data-testid="tab-controls">
          <Button
            type="button"
            onClick={() => setActiveTab("multibagger")}
            className={activeTab === "multibagger" ? "bg-slate-900 text-white hover:bg-slate-800" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"}
            data-testid="tab-multibagger"
          >
            <BarChart3 size={16} />
            Multibagger Finder
          </Button>
          <Button
            type="button"
            onClick={() => setActiveTab("fno")}
            className={activeTab === "fno" ? "bg-slate-900 text-white hover:bg-slate-800" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"}
            data-testid="tab-fno"
          >
            <TrendingUp size={16} />
            F&O Signals
          </Button>
          {user.role === "admin" ? (
            <Button
              type="button"
              onClick={() => {
                setActiveTab("admin");
                loadAdminUsers();
              }}
              className={activeTab === "admin" ? "bg-slate-900 text-white hover:bg-slate-800" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"}
              data-testid="tab-admin"
            >
              <Shield size={16} />
              Admin Credits
            </Button>
          ) : null}
        </section>

        {activeTab === "multibagger" ? (
          <section className="space-y-6" data-testid="multibagger-section">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-lg">Multibagger Discovery</CardTitle>
                <Button
                  type="button"
                  onClick={generateMultibaggers}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="generate-multibagger-button"
                >
                  <RefreshCw size={16} className={multibaggerLoading ? "animate-spin" : ""} />
                  {multibaggerLoading ? "Finding..." : "Get New Multibagger (-1 credit)"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="max-w-xl">
                  <Slider
                    min={0}
                    max={100}
                    step={1}
                    value={[minScore]}
                    onValueChange={(value) => setMinScore(value[0])}
                    data-testid="multibagger-score-slider"
                  />
                </div>
                <p className="text-sm text-slate-600" data-testid="multibagger-filter-note">
                  Score filter ≥ <span className="font-mono">{minScore}</span>
                </p>
                {multibaggerError ? (
                  <p className="text-sm text-rose-600" data-testid="multibagger-error">{multibaggerError}</p>
                ) : null}
                {!multibaggerData ? (
                  <p className="text-sm text-slate-500" data-testid="multibagger-pre-note">
                    No multibagger list yet. Click <strong>Get New Multibagger</strong> to run live analysis.
                  </p>
                ) : (
                  <p className="text-xs text-slate-500" data-testid="multibagger-refresh-time">
                    Refreshed at: {formatTime(multibaggerData.analysis_refreshed_at)}
                  </p>
                )}
              </CardContent>
            </Card>

            {multibaggerData ? (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg" data-testid="multibagger-table-title">Top Multibagger Candidates</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-200" data-testid="multibagger-table-wrapper">
                    <Table data-testid="multibagger-table">
                      <TableHeader className="bg-slate-50">
                        <TableRow>
                          <TableHead>Symbol</TableHead>
                          <TableHead>Company</TableHead>
                          <TableHead>Sector</TableHead>
                          <TableHead>LTP</TableHead>
                          <TableHead>Market Cap (Cr)</TableHead>
                          <TableHead>PE</TableHead>
                          <TableHead>52W High</TableHead>
                          <TableHead>52W Low</TableHead>
                          <TableHead>Tier Pass</TableHead>
                          <TableHead>Score</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredCandidates.map((stock) => (
                          <TableRow key={stock.symbol} data-testid={`stock-row-${stock.symbol.toLowerCase()}`}>
                            <TableCell className="font-mono">{stock.symbol}</TableCell>
                            <TableCell>{stock.company_name}</TableCell>
                            <TableCell>{stock.sector}</TableCell>
                            <TableCell className="font-mono">₹{formatNumber(stock.ltp)}</TableCell>
                            <TableCell className="font-mono">{formatNumber(stock.market_cap_cr, 0)}</TableCell>
                            <TableCell className="font-mono">{formatNumber(stock.pe_ratio)}</TableCell>
                            <TableCell className="font-mono">{formatNumber(stock.year_high)}</TableCell>
                            <TableCell className="font-mono">{formatNumber(stock.year_low)}</TableCell>
                            <TableCell className="font-mono">{stock.tier_pass_count}/8</TableCell>
                            <TableCell>
                              <Badge className={`border ${getScoreClass(stock.is_potential_multibagger, stock.multibagger_score)}`}>
                                {stock.is_potential_multibagger ? `POTENTIAL ${stock.multibagger_score}` : stock.multibagger_score}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </section>
        ) : null}

        {activeTab === "fno" ? (
          <section className="space-y-6" data-testid="fno-section">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-lg">F&O Live Signal Generation</CardTitle>
                <Button
                  type="button"
                  onClick={() => generateFno()}
                  className="bg-slate-900 text-white hover:bg-slate-800"
                  data-testid="generate-fno-button"
                >
                  <RefreshCw size={16} className={fnoLoading ? "animate-spin" : ""} />
                  {fnoLoading ? "Generating..." : "Generate F&O Signals (-2 credits)"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                <form
                  className="flex flex-col gap-3 sm:flex-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    generateFno(script);
                  }}
                  data-testid="custom-fno-form"
                >
                  <Input
                    value={script}
                    onChange={(event) => setScript(event.target.value.toUpperCase())}
                    placeholder="Enter script, e.g., NIFTY10MAR26500PE"
                    className="font-mono"
                    data-testid="custom-script-input"
                  />
                  <Button type="submit" className="bg-white text-slate-800 border border-slate-300 hover:bg-slate-100" data-testid="generate-custom-fno-button">
                    Run Custom Script (-2 credits)
                  </Button>
                </form>
                {fnoError ? <p className="text-sm text-rose-600" data-testid="fno-error">{fnoError}</p> : null}
                {!fnoData ? (
                  <p className="text-sm text-slate-500" data-testid="fno-pre-note">
                    No F&O signals yet. Click <strong>Generate F&O Signals</strong> for live market analytics.
                  </p>
                ) : (
                  <p className="text-xs text-slate-500" data-testid="fno-refresh-time">
                    Refreshed at: {formatTime(fnoData.analysis_refreshed_at)}
                  </p>
                )}
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="space-y-6 lg:col-span-8">
                {fnoData?.potential_signals?.length ? (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">Potential Profitable Trade Signals</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {fnoData.potential_signals.map((signal) => (
                        <Card key={signal.script} className="border border-slate-200">
                          <CardHeader className="space-y-3 border-b border-slate-100">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <CardTitle className="text-base font-semibold">{signal.script}</CardTitle>
                              <div className="flex items-center gap-2">
                                <Badge className={`border ${getQualityClass(signal.signal_quality)}`}>{signal.signal_quality}</Badge>
                                <Badge className={`border ${getDirectionClass(signal.direction)}`}>{signal.direction}</Badge>
                              </div>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-sm text-slate-600 md:grid-cols-4">
                              <p>Underlying: <span className="font-mono">{signal.underlying}</span></p>
                              <p>Expiry: <span className="font-mono">{signal.expiry}</span></p>
                              <p>Strike: <span className="font-mono">{formatNumber(signal.strike, 0)}</span></p>
                              <p>Lot: <span className="font-mono">{signal.lot_size}</span></p>
                            </div>
                          </CardHeader>
                          <CardContent className="grid grid-cols-1 gap-4 pt-4 md:grid-cols-2">
                            <div className="space-y-1 text-sm">
                              <p>Entry: <span className="font-mono">₹{formatNumber(signal.entry_price)}</span></p>
                              <p>Stop Loss: <span className="font-mono">₹{formatNumber(signal.stop_loss)}</span></p>
                              <p>Target1: <span className="font-mono">₹{formatNumber(signal.target1)}</span></p>
                              <p>Target2: <span className="font-mono">₹{formatNumber(signal.target2)}</span></p>
                            </div>
                            <div className="space-y-1 text-sm">
                              <p>Confluence: <span className="font-mono">{signal.confluence_score}/100</span></p>
                              <p>R:R T1: <span className="font-mono">{formatNumber(signal.risk_reward_target1)}</span></p>
                              <p>R:R T2: <span className="font-mono">{formatNumber(signal.risk_reward_target2)}</span></p>
                              <p>Rationale: <span className="font-mono text-xs">{signal.trigger_factors.join(" | ")}</span></p>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </CardContent>
                  </Card>
                ) : null}

                {fnoData?.custom_signal ? (
                  <Card data-testid="custom-signal-card">
                    <CardHeader>
                      <CardTitle className="text-lg">Custom Script Signal</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <p>Script: <span className="font-mono">{fnoData.custom_signal.script}</span></p>
                      <p>Direction: <span className="font-mono">{fnoData.custom_signal.direction}</span></p>
                      <p>Confluence: <span className="font-mono">{fnoData.custom_signal.confluence_score}/100</span></p>
                      <p>Entry/SL/Targets: <span className="font-mono">₹{formatNumber(fnoData.custom_signal.entry_price)} / ₹{formatNumber(fnoData.custom_signal.stop_loss)} / ₹{formatNumber(fnoData.custom_signal.target1)} / ₹{formatNumber(fnoData.custom_signal.target2)}</span></p>
                    </CardContent>
                  </Card>
                ) : null}
              </div>

              <div className="lg:col-span-4">
                <div className="sticky top-4">
                  <Card data-testid="top4-trades-panel">
                    <CardHeader>
                      <CardTitle className="text-lg">Top 4 Best Trade Now</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {bestTrades.length ? (
                        bestTrades.map((trade) => (
                          <div key={`top-${trade.script}`} className="rounded-md border border-slate-200 bg-white p-3 text-sm" data-testid={`top-trade-${trade.script.toLowerCase()}`}>
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <p className="font-mono text-xs font-semibold">{trade.script}</p>
                              <Badge className={`border ${getDirectionClass(trade.direction)}`}>{trade.direction}</Badge>
                            </div>
                            <p>Entry: <span className="font-mono">₹{formatNumber(trade.entry_price)}</span></p>
                            <p>SL: <span className="font-mono">₹{formatNumber(trade.stop_loss)}</span></p>
                            <p>T1/T2: <span className="font-mono">₹{formatNumber(trade.target1)} / ₹{formatNumber(trade.target2)}</span></p>
                            <p>Confidence: <span className="font-mono">{trade.confluence_score}/100 ({trade.signal_quality})</span></p>
                            <p className="text-xs text-slate-500">{trade.trigger_factors.slice(0, 2).join(" | ")}</p>
                          </div>
                        ))
                      ) : (
                        <p className="text-sm text-slate-500" data-testid="top4-empty-note">Generate F&O signals to populate top trades.</p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "admin" && user.role === "admin" ? (
          <section className="space-y-6" data-testid="admin-section">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-lg">Admin User & Credit Management (CRUD)</CardTitle>
                <Button
                  type="button"
                  onClick={loadAdminUsers}
                  className="bg-slate-900 text-white hover:bg-slate-800"
                  data-testid="admin-refresh-users-button"
                >
                  <Users size={16} />
                  Refresh Users
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={createUserByAdmin} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="admin-create-user-form">
                  <Input
                    value={adminForm.password}
                    onChange={(event) => setAdminForm((prev) => ({ ...prev, password: event.target.value }))}
                    placeholder="New user password"
                    data-testid="admin-new-password-input"
                  />
                  <Input
                    type="number"
                    min="0"
                    value={adminForm.initial_credits}
                    onChange={(event) => setAdminForm((prev) => ({ ...prev, initial_credits: Number(event.target.value) }))}
                    placeholder="Initial credits"
                    data-testid="admin-new-credits-input"
                  />
                  <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="admin-create-user-button">
                    Create User
                  </Button>
                </form>
                {adminError ? <p className="text-sm text-rose-600" data-testid="admin-error">{adminError}</p> : null}

                {adminLoading ? (
                  <p className="text-sm text-slate-500" data-testid="admin-loading">Loading users...</p>
                ) : (
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-200" data-testid="admin-users-table-wrapper">
                    <Table data-testid="admin-users-table">
                      <TableHeader className="bg-slate-50">
                        <TableRow>
                          <TableHead>User Key</TableHead>
                          <TableHead>Role</TableHead>
                          <TableHead>Credits</TableHead>
                          <TableHead>Created</TableHead>
                          <TableHead>Set Credits</TableHead>
                          <TableHead>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {adminUsers.map((row) => (
                          <TableRow key={row.user_key} data-testid={`admin-user-row-${row.user_key}`}>
                            <TableCell className="font-mono text-xs">{row.user_key}</TableCell>
                            <TableCell>
                              <Badge className="border bg-white text-slate-700">{row.role}</Badge>
                            </TableCell>
                            <TableCell className="font-mono">{row.credits}</TableCell>
                            <TableCell className="text-xs">{formatTime(row.created_at)}</TableCell>
                            <TableCell>
                              <Input
                                type="number"
                                min="0"
                                value={creditEditMap[row.user_key] ?? row.credits}
                                onChange={(event) =>
                                  setCreditEditMap((prev) => ({
                                    ...prev,
                                    [row.user_key]: Number(event.target.value),
                                  }))
                                }
                                className="h-8 w-28"
                                data-testid={`admin-credit-input-${row.user_key}`}
                              />
                            </TableCell>
                            <TableCell className="space-x-2">
                              <Button
                                type="button"
                                onClick={() => updateCredits(row.user_key)}
                                className="h-8 bg-slate-900 px-3 text-white hover:bg-slate-800"
                                data-testid={`admin-update-credit-${row.user_key}`}
                              >
                                Update
                              </Button>
                              {row.role !== "admin" ? (
                                <Button
                                  type="button"
                                  onClick={() => deleteUser(row.user_key)}
                                  className="h-8 border border-rose-300 bg-white px-3 text-rose-600 hover:bg-rose-50"
                                  data-testid={`admin-delete-user-${row.user_key}`}
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
          </section>
        ) : null}

        <section className="mt-8" data-testid="compliance-disclaimer-section">
          <Card className="border border-amber-200 bg-amber-50">
            <CardContent className="pt-5">
              <p className="text-sm font-semibold text-amber-800">Personal Testing & Educational Disclaimer (SEBI-aligned)</p>
              <p className="mt-2 text-xs leading-relaxed text-amber-900">
                This application is for educational research and personal testing only. Outputs are analytics-based simulations and not investment advice,
                recommendation, portfolio management service, or guaranteed-profit claims. Trading involves risk. Consult a SEBI-registered advisor for real investments.
              </p>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
