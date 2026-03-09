import { Fragment, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  BarChart3,
  GaugeCircle,
  Home,
  KeyRound,
  LogOut,
  RefreshCw,
  Shield,
  Sparkles,
  TrendingUp,
  UserCog,
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

  const [adminUsers, setAdminUsers] = useState([]);
  const [adminError, setAdminError] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);
  const [createForm, setCreateForm] = useState({
    username: "",
    role: "user",
    initial_credits: 0,
    quota_limit: 10,
  });
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

  const syncCredits = (credits) => {
    setMe((prev) => (prev ? { ...prev, credits } : prev));
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

  const loadAdminUsers = async () => {
    setAdminLoading(true);
    setAdminError("");
    try {
      const response = await axios.get(`${API}/admin/users`, { headers: authHeaders });
      const rows = response.data || [];
      setAdminUsers(rows);
      const creditMap = {};
      const quotaMap = {};
      rows.forEach((row) => {
        creditMap[row.user_key] = row.credits;
        quotaMap[row.user_key] = row.quota_limit;
      });
      setCreditEdit(creditMap);
      setQuotaEdit(quotaMap);
    } catch (error) {
      setAdminError(error?.response?.data?.detail || "Unable to load users");
    } finally {
      setAdminLoading(false);
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
              <p className="font-mono text-sm text-cyan-300">Multibagger:1 | F&O:2</p>
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
          {isAdmin ? (
            <Button
              type="button"
              onClick={() => {
                setCurrentPage("admin");
                loadAdminUsers();
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
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
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
            </div>
          </section>
        ) : null}

        {currentPage === "multibagger" ? (
          <section className="space-y-6" data-testid="multibagger-page">
            <Card className="border-slate-800 bg-slate-950/70">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">Multibagger Discovery</CardTitle>
                <Button
                  type="button"
                  onClick={generateMultibagger}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="multibagger-generate-button"
                >
                  <RefreshCw size={16} className={multibaggerLoading ? "animate-spin" : ""} />
                  {multibaggerLoading ? "Finding..." : "Find Multibagger"}
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
                    Nothing shown yet. Click <strong>Find Multibagger</strong> to run live analysis.
                  </p>
                ) : (
                  <p className="text-xs text-slate-400" data-testid="multibagger-refreshed-at">
                    Refreshed at: {formatTime(multibaggerData.analysis_refreshed_at)} | Charged: {multibaggerData.cost_charged}
                  </p>
                )}
              </CardContent>
            </Card>

            {multibaggerData ? (
              <Card className="border-slate-800 bg-slate-950/70">
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
                            <TableRow key={`${row.symbol}-target`} data-testid={`multibagger-target-row-${row.symbol.toLowerCase()}`}>
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

                            <TableRow key={`${row.symbol}-roi`} data-testid={`multibagger-roi-row-${row.symbol.toLowerCase()}`}>
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
            <Card className="border-slate-800 bg-slate-950/70">
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle className="text-white">F&O Projections</CardTitle>
                <Button
                  type="button"
                  onClick={() => generateFnoProjection()}
                  className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
                  data-testid="fno-generate-button"
                >
                  <RefreshCw size={16} className={fnoLoading ? "animate-spin" : ""} />
                  {fnoLoading ? "Generating..." : "Generate F&O Projections"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    generateFnoProjection(customScript);
                  }}
                  className="flex flex-col gap-3 sm:flex-row"
                  data-testid="fno-custom-script-form"
                >
                  <Input
                    value={customScript}
                    onChange={(event) => setCustomScript(event.target.value.toUpperCase())}
                    placeholder="Run custom script or symbol (e.g. NIFTY10MAR26500PE / RELIANCE)"
                    className="font-mono border-slate-700 bg-slate-900 text-slate-100"
                    data-testid="fno-custom-script-input"
                  />
                  <Button
                    type="submit"
                    className="border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"
                    data-testid="fno-custom-script-submit"
                  >
                    Run Custom Projection
                  </Button>
                </form>
                {fnoError ? <p className="text-sm text-rose-400" data-testid="fno-error">{fnoError}</p> : null}
                {!fnoData ? (
                  <p className="text-sm text-slate-400" data-testid="fno-empty-note">
                    Nothing shown yet. Click <strong>Generate F&O Projections</strong> for live analysis.
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
                      <Card key={pane.index_name} className="border-slate-800 bg-slate-950/70" data-testid={`pane-${pane.index_name.toLowerCase()}`}>
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
                                  <div key={signal.script} className="rounded-md border border-slate-800 bg-slate-900/70 p-2 text-xs">
                                    <div className="mb-1 flex items-center justify-between">
                                      <span className="font-mono text-cyan-200">{signal.script}</span>
                                      <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                                    </div>
                                    <p>Entry/SL/T1/T2: ₹{formatNumber(signal.entry_price)} / ₹{formatNumber(signal.stop_loss)} / ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                                    <p>Confluence: {signal.confluence_score} ({signal.signal_quality})</p>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400">No assured directional setup currently.</p>
                            )}
                          </div>

                          <div data-testid={`pane-nondirectional-${pane.index_name.toLowerCase()}`}>
                            <p className="mb-2 text-sm font-semibold text-amber-300">Non-Directional Strategies</p>
                            {pane.non_directional_strategies.length ? (
                              <div className="space-y-2">
                                {pane.non_directional_strategies.map((item) => (
                                  <div key={`${pane.index_name}-${item.strike}`} className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs">
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
                        </CardContent>
                      </Card>
                    ))}
                  </div>

                  <Card className="border-slate-800 bg-slate-950/70" data-testid="stock-fno-bottom-panel">
                    <CardHeader>
                      <CardTitle className="text-white">Profitable F&O Signals — Individual Stocks</CardTitle>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {fnoData.stock_signals?.length ? (
                        fnoData.stock_signals.map((signal) => (
                          <div key={signal.script} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs" data-testid={`stock-fno-signal-${signal.script.toLowerCase()}`}>
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <p className="font-mono text-cyan-200">{signal.script}</p>
                              <Badge className={`border ${directionBadge(signal.direction)}`}>{signal.direction}</Badge>
                            </div>
                            <p>Entry: ₹{formatNumber(signal.entry_price)}</p>
                            <p>SL: ₹{formatNumber(signal.stop_loss)}</p>
                            <p>T1/T2: ₹{formatNumber(signal.target1)} / ₹{formatNumber(signal.target2)}</p>
                            <p>Confidence: {signal.confluence_score}</p>
                          </div>
                        ))
                      ) : (
                        <p className="text-sm text-slate-400">No stock F&O opportunities found in this cycle.</p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                <div className="xl:col-span-4">
                  <div className="sticky top-4 space-y-4">
                    <Card className="border-slate-800 bg-slate-950/70" data-testid="top4-trades-panel">
                      <CardHeader>
                        <CardTitle className="text-white">Top 4 Best Trade Now</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        {fnoData.top_trades?.length ? (
                          fnoData.top_trades.map((trade) => (
                            <div key={trade.script} className="rounded-md border border-slate-800 bg-slate-900/70 p-3 text-xs" data-testid={`top4-trade-${trade.script.toLowerCase()}`}>
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
                      <Card className="border-slate-800 bg-slate-950/70" data-testid="custom-script-result-card">
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

        {currentPage === "admin" && isAdmin ? (
          <section className="space-y-6" data-testid="admin-page">
            <Card className="border-slate-800 bg-slate-950/70">
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
                          <TableRow key={row.user_key} data-testid={`admin-row-${row.user_key}`}>
                            <TableCell className="font-mono text-xs text-cyan-200">{row.credential_label}</TableCell>
                            <TableCell>{row.role}</TableCell>
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
