import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Activity, BarChart3, TrendingDown, TrendingUp } from "lucide-react";
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
  if (value === null || value === undefined) {
    return "-";
  }
  return Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
};

const getScoreBadgeClass = (score) => {
  if (score >= 70) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (score >= 40) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-rose-50 text-rose-700 border-rose-200";
};

const getDirectionBadgeClass = (direction) => {
  if (direction === "BULLISH") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (direction === "BEARISH") return "bg-rose-50 text-rose-700 border-rose-200";
  return "bg-slate-100 text-slate-700 border-slate-200";
};

export default function App() {
  const [activeTab, setActiveTab] = useState("multibagger");
  const [candidates, setCandidates] = useState([]);
  const [multibaggerLoading, setMultibaggerLoading] = useState(true);
  const [multibaggerError, setMultibaggerError] = useState("");
  const [minScore, setMinScore] = useState(40);

  const [indexSignals, setIndexSignals] = useState([]);
  const [signalsLoading, setSignalsLoading] = useState(true);
  const [signalsError, setSignalsError] = useState("");

  const [script, setScript] = useState("NIFTY10MAR26500PE");
  const [customSignal, setCustomSignal] = useState(null);
  const [customLoading, setCustomLoading] = useState(false);
  const [customError, setCustomError] = useState("");

  useEffect(() => {
    const loadMultibagger = async () => {
      setMultibaggerLoading(true);
      setMultibaggerError("");
      try {
        const response = await axios.get(`${API}/multibagger/candidates`);
        setCandidates(response.data || []);
      } catch {
        setMultibaggerError("Failed to load multibagger candidates.");
      } finally {
        setMultibaggerLoading(false);
      }
    };

    const loadIndexSignals = async () => {
      setSignalsLoading(true);
      setSignalsError("");
      try {
        const response = await axios.get(`${API}/fno/signals/index`);
        setIndexSignals(response.data || []);
      } catch {
        setSignalsError("Failed to load index F&O signals.");
      } finally {
        setSignalsLoading(false);
      }
    };

    loadMultibagger();
    loadIndexSignals();
  }, []);

  const filteredCandidates = useMemo(
    () => candidates.filter((stock) => stock.multibagger_score >= minScore),
    [candidates, minScore],
  );

  const handleCustomSignal = async (event) => {
    event.preventDefault();
    const normalizedScript = script.trim().toUpperCase();
    if (!normalizedScript) {
      setCustomError("Please enter a valid script.");
      setCustomSignal(null);
      return;
    }

    setCustomLoading(true);
    setCustomError("");
    try {
      const response = await axios.get(`${API}/fno/signal/${encodeURIComponent(normalizedScript)}`);
      setCustomSignal(response.data);
      setScript(normalizedScript);
    } catch (error) {
      const message = error?.response?.data?.detail || "Unable to fetch custom script signal.";
      setCustomError(message);
      setCustomSignal(null);
    } finally {
      setCustomLoading(false);
    }
  };

  const SignalCard = ({ signal, cardTestId }) => (
    <Card
      className="border-slate-200 shadow-sm transition-shadow duration-200 hover:shadow-md"
      data-testid={cardTestId}
    >
      <CardHeader className="space-y-3 border-b border-slate-100">
        <div className="flex items-start justify-between gap-4">
          <CardTitle className="text-base font-semibold text-slate-900" data-testid={`${cardTestId}-script`}>
            {signal.script}
          </CardTitle>
          <Badge
            className={`border font-medium ${getDirectionBadgeClass(signal.direction)}`}
            data-testid={`${cardTestId}-direction`}
          >
            {signal.direction}
          </Badge>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm text-slate-600 md:grid-cols-4">
          <div data-testid={`${cardTestId}-underlying`}>Underlying: <span className="font-mono">{signal.underlying}</span></div>
          <div data-testid={`${cardTestId}-expiry`}>Expiry: <span className="font-mono">{signal.expiry}</span></div>
          <div data-testid={`${cardTestId}-strike`}>Strike: <span className="font-mono">{formatNumber(signal.strike, 0)}</span></div>
          <div data-testid={`${cardTestId}-lot-size`}>Lot: <span className="font-mono">{signal.lot_size}</span></div>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 pt-6 lg:grid-cols-2">
        <div className="space-y-2 text-sm text-slate-700">
          <p className="text-slate-500" data-testid={`${cardTestId}-strategy`}>{signal.strategy}</p>
          <p data-testid={`${cardTestId}-entry`}>Entry: <span className="font-mono">₹{formatNumber(signal.entry_price)}</span></p>
          <p data-testid={`${cardTestId}-stop-loss`}>Stop Loss: <span className="font-mono">₹{formatNumber(signal.stop_loss)}</span></p>
          <p data-testid={`${cardTestId}-target1`}>Target 1: <span className="font-mono">₹{formatNumber(signal.target1)}</span></p>
          <p data-testid={`${cardTestId}-target2`}>Target 2: <span className="font-mono">₹{formatNumber(signal.target2)}</span></p>
        </div>
        <div className="space-y-2 text-sm text-slate-700">
          <p data-testid={`${cardTestId}-underlying-ltp`}>
            Underlying LTP: <span className="font-mono">₹{formatNumber(signal.underlying_ltp)}</span>
          </p>
          <p data-testid={`${cardTestId}-option-ltp`}>
            Option LTP: <span className="font-mono">₹{formatNumber(signal.option_ltp)}</span>
          </p>
          <p data-testid={`${cardTestId}-rr1`}>
            Risk/Reward T1: <span className="font-mono">{formatNumber(signal.risk_reward_target1)}</span>
          </p>
          <p data-testid={`${cardTestId}-rr2`}>
            Risk/Reward T2: <span className="font-mono">{formatNumber(signal.risk_reward_target2)}</span>
          </p>
          <p data-testid={`${cardTestId}-confluence`}>
            Confluence Score: <span className="font-mono">{signal.confluence_score}/100</span>
          </p>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900" data-testid="app-shell">
      <div className="architect-grid-overlay" />
      <div className="relative mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
        <header className="mb-8 space-y-4" data-testid="app-header">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600" data-testid="app-header-chip">
            <Activity size={14} />
            Live Market Dashboard
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl" data-testid="app-title">
            AI Stock Research – Multibagger & F&O
          </h1>
          <p className="max-w-3xl text-sm text-slate-500 sm:text-base" data-testid="app-subtitle">
            Minimal dashboard for live Indian market screening and simplified options signals.
          </p>
        </header>

        <section className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-12" data-testid="summary-section">
          <Card className="md:col-span-4" data-testid="summary-card-candidates">
            <CardContent className="pt-6">
              <p className="text-sm text-slate-500" data-testid="summary-candidates-label">Candidates loaded</p>
              <p className="mt-2 font-mono text-3xl font-semibold" data-testid="summary-candidates-value">{candidates.length}</p>
            </CardContent>
          </Card>
          <Card className="md:col-span-4" data-testid="summary-card-filtered">
            <CardContent className="pt-6">
              <p className="text-sm text-slate-500" data-testid="summary-filtered-label">Above min score</p>
              <p className="mt-2 font-mono text-3xl font-semibold" data-testid="summary-filtered-value">{filteredCandidates.length}</p>
            </CardContent>
          </Card>
          <Card className="md:col-span-4" data-testid="summary-card-signals">
            <CardContent className="pt-6">
              <p className="text-sm text-slate-500" data-testid="summary-signals-label">Index F&O signals</p>
              <p className="mt-2 font-mono text-3xl font-semibold" data-testid="summary-signals-value">{indexSignals.length}</p>
            </CardContent>
          </Card>
        </section>

        <section className="mb-8 flex flex-wrap gap-3" data-testid="tab-controls">
          <Button
            type="button"
            onClick={() => setActiveTab("multibagger")}
            className={
              activeTab === "multibagger"
                ? "bg-slate-900 text-white hover:bg-slate-800"
                : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
            }
            data-testid="tab-multibagger-button"
          >
            <BarChart3 size={16} />
            Multibagger Finder
          </Button>
          <Button
            type="button"
            onClick={() => setActiveTab("fno")}
            className={
              activeTab === "fno"
                ? "bg-slate-900 text-white hover:bg-slate-800"
                : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
            }
            data-testid="tab-fno-button"
          >
            <TrendingUp size={16} />
            F&O Signals
          </Button>
        </section>

        {activeTab === "multibagger" ? (
          <section className="space-y-6" data-testid="multibagger-view">
            <Card data-testid="multibagger-filter-card">
              <CardHeader>
                <CardTitle className="text-lg text-slate-900" data-testid="multibagger-filter-title">Minimum Score Filter</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="max-w-xl" data-testid="multibagger-score-slider-container">
                  <Slider
                    min={0}
                    max={100}
                    step={1}
                    value={[minScore]}
                    onValueChange={(value) => setMinScore(value[0])}
                    data-testid="multibagger-score-slider"
                  />
                </div>
                <p className="text-sm text-slate-600" data-testid="multibagger-score-value">
                  Showing stocks with score <span className="font-mono">≥ {minScore}</span>
                </p>
              </CardContent>
            </Card>

            <Card data-testid="multibagger-table-card">
              <CardHeader>
                <CardTitle className="text-lg text-slate-900" data-testid="multibagger-table-title">Top Multibagger Candidates</CardTitle>
              </CardHeader>
              <CardContent>
                {multibaggerLoading ? (
                  <p className="text-sm text-slate-500" data-testid="multibagger-loading">Loading candidates...</p>
                ) : multibaggerError ? (
                  <p className="text-sm text-rose-600" data-testid="multibagger-error">{multibaggerError}</p>
                ) : (
                  <div className="relative w-full overflow-auto rounded-lg border border-slate-200" data-testid="multibagger-table-wrapper">
                    <Table data-testid="multibagger-table">
                      <TableHeader className="bg-slate-50">
                        <TableRow data-testid="multibagger-header-row">
                          <TableHead data-testid="head-symbol">Symbol</TableHead>
                          <TableHead data-testid="head-company">Company</TableHead>
                          <TableHead data-testid="head-sector">Sector</TableHead>
                          <TableHead data-testid="head-ltp">LTP</TableHead>
                          <TableHead data-testid="head-market-cap">Market Cap (Cr)</TableHead>
                          <TableHead data-testid="head-pe">PE</TableHead>
                          <TableHead data-testid="head-52wh">52W High</TableHead>
                          <TableHead data-testid="head-52wl">52W Low</TableHead>
                          <TableHead data-testid="head-score">Score</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredCandidates.map((stock) => (
                          <TableRow key={stock.symbol} data-testid={`stock-row-${stock.symbol.toLowerCase()}`}>
                            <TableCell className="font-mono" data-testid={`stock-symbol-${stock.symbol.toLowerCase()}`}>{stock.symbol}</TableCell>
                            <TableCell data-testid={`stock-company-${stock.symbol.toLowerCase()}`}>{stock.company_name}</TableCell>
                            <TableCell data-testid={`stock-sector-${stock.symbol.toLowerCase()}`}>{stock.sector || "-"}</TableCell>
                            <TableCell className="font-mono" data-testid={`stock-ltp-${stock.symbol.toLowerCase()}`}>₹{formatNumber(stock.ltp)}</TableCell>
                            <TableCell className="font-mono" data-testid={`stock-marketcap-${stock.symbol.toLowerCase()}`}>{formatNumber(stock.market_cap_cr, 0)}</TableCell>
                            <TableCell className="font-mono" data-testid={`stock-pe-${stock.symbol.toLowerCase()}`}>{formatNumber(stock.pe_ratio)}</TableCell>
                            <TableCell className="font-mono" data-testid={`stock-yearhigh-${stock.symbol.toLowerCase()}`}>{formatNumber(stock.year_high)}</TableCell>
                            <TableCell className="font-mono" data-testid={`stock-yearlow-${stock.symbol.toLowerCase()}`}>{formatNumber(stock.year_low)}</TableCell>
                            <TableCell data-testid={`stock-score-${stock.symbol.toLowerCase()}`}>
                              <Badge className={`border ${getScoreBadgeClass(stock.multibagger_score)}`}>
                                {stock.multibagger_score}
                              </Badge>
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
        ) : (
          <section className="space-y-8" data-testid="fno-view">
            <Card data-testid="index-signals-card">
              <CardHeader>
                <CardTitle className="text-lg text-slate-900" data-testid="index-signals-title">Index F&O Signals</CardTitle>
              </CardHeader>
              <CardContent>
                {signalsLoading ? (
                  <p className="text-sm text-slate-500" data-testid="index-signals-loading">Loading index signals...</p>
                ) : signalsError ? (
                  <p className="text-sm text-rose-600" data-testid="index-signals-error">{signalsError}</p>
                ) : (
                  <div className="grid grid-cols-1 gap-6" data-testid="index-signals-grid">
                    {indexSignals.map((signal) => (
                      <SignalCard
                        key={signal.script}
                        signal={signal}
                        cardTestId={`index-signal-card-${signal.script.toLowerCase()}`}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card data-testid="custom-script-card">
              <CardHeader>
                <CardTitle className="text-lg text-slate-900" data-testid="custom-script-title">Check Custom Script</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={handleCustomSignal} className="flex flex-col gap-3 sm:flex-row" data-testid="custom-script-form">
                  <Input
                    value={script}
                    onChange={(event) => setScript(event.target.value.toUpperCase())}
                    placeholder="Enter script, e.g., NIFTY10MAR26500PE"
                    className="font-mono"
                    data-testid="custom-script-input"
                  />
                  <Button
                    type="submit"
                    className="bg-slate-900 text-white hover:bg-slate-800"
                    data-testid="custom-script-submit-button"
                  >
                    {customLoading ? "Checking..." : "Get Signal"}
                  </Button>
                </form>

                {customError ? (
                  <p className="text-sm text-rose-600" data-testid="custom-script-error">{customError}</p>
                ) : null}

                {customSignal ? (
                  <div className="pt-2" data-testid="custom-signal-result">
                    <SignalCard signal={customSignal} cardTestId="custom-signal-card" />
                  </div>
                ) : (
                  <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500" data-testid="custom-signal-empty-state">
                    <TrendingDown className="mb-2" size={16} />
                    Enter a valid script and submit to view the signal card.
                  </div>
                )}
              </CardContent>
            </Card>
          </section>
        )}
      </div>
    </main>
  );
}
