import { useMemo, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Table, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber, formatTime, scoreBadge } from "@/utils/formatters";
import { readNDJSONStream } from "@/components/Shared/NDJSONStreamConsumer";
import { MultibaggerCandidateCard } from "./MultibaggerCandidateCard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function MultibaggerDashboard({ authHeaders, syncCredits }) {
  const [multibaggerData, setMultibaggerData] = useState(null);
  const [multibaggerLoading, setMultibaggerLoading] = useState(false);
  const [multibaggerError, setMultibaggerError] = useState("");
  const [multibaggerProgress, setMultibaggerProgress] = useState("");
  const [minScore, setMinScore] = useState(60);
  const [customMbSymbol, setCustomMbSymbol] = useState("");
  const [customMbResult, setCustomMbResult] = useState(null);
  const [customMbLoading, setCustomMbLoading] = useState(false);
  const [customMbError, setCustomMbError] = useState("");
  const [expandedMbBands, setExpandedMbBands] = useState({});

  const filteredMultibaggers = useMemo(() => {
    const rows = multibaggerData?.candidates || [];
    return rows.filter((row) => row.multibagger_score >= minScore);
  }, [multibaggerData, minScore]);

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

  const searchCustomMbStock = async (e) => {
    e.preventDefault();
    if (!customMbSymbol.trim()) return;
    setCustomMbError("");
    setCustomMbResult(null);
    setCustomMbLoading(true);
    try {
      const axios = (await import("axios")).default;
      const response = await axios.post(
        `${API}/multibagger/custom-search`,
        { symbol: customMbSymbol.trim().toUpperCase() },
        { headers: authHeaders },
      );
      setCustomMbResult(response.data);
    } catch (error) {
      setCustomMbError(error?.response?.data?.detail || `No data found for '${customMbSymbol}'. Check the NSE symbol.`);
    } finally {
      setCustomMbLoading(false);
    }
  };

  return (
    <section className="space-y-6" data-testid="multibagger-page">
      <Card className="result-card border-slate-800 bg-slate-950/70">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
          <CardTitle className="text-white">Multibagger Discovery</CardTitle>
          <Button type="button" onClick={generateMultibagger} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="multibagger-generate-button">
            <RefreshCw size={16} className={multibaggerLoading ? "animate-spin" : ""} />
            {multibaggerLoading ? (multibaggerProgress || "Finding...") : "Find Multibagger (-2)"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="max-w-xl" data-testid="multibagger-slider-block">
            <Slider min={0} max={100} step={1} value={[minScore]} onValueChange={(value) => setMinScore(value[0])} data-testid="multibagger-score-slider" />
          </div>
          <p className="text-sm text-slate-300" data-testid="multibagger-score-note">
            Minimum score: <span className="font-mono text-cyan-300">{minScore}</span>
          </p>
          <form onSubmit={searchCustomMbStock} className="flex flex-col gap-2 sm:flex-row" data-testid="mb-custom-search-form">
            <Input value={customMbSymbol} onChange={(e) => setCustomMbSymbol(e.target.value.toUpperCase())} placeholder="Search any NSE symbol (e.g. RELIANCE, INFY)" className="font-mono border-slate-700 bg-slate-900 text-slate-100" data-testid="mb-custom-search-input" />
            <Button type="submit" disabled={customMbLoading || !customMbSymbol.trim()} className="border border-cyan-700 bg-cyan-900/30 text-cyan-300 hover:bg-cyan-800/50" data-testid="mb-custom-search-btn">
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
                  <MultibaggerCandidateCard
                    key={row.symbol}
                    row={row}
                    expanded={expandedMbBands[row.symbol]}
                    onToggleBands={() => setExpandedMbBands(prev => ({...prev, [row.symbol]: !prev[row.symbol]}))}
                  />
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
              <Badge className={`border ${scoreBadge(customMbResult.is_potential_multibagger)}`}>Score: {customMbResult.multibagger_score}</Badge>
              <Badge className={`border ${scoreBadge(customMbResult.is_potential_multibagger)}`}>{customMbResult.is_potential_multibagger ? "POTENTIAL MULTIBAGGER" : "WATCHLIST"}</Badge>
              <button onClick={() => setCustomMbResult(null)} className="text-slate-400 hover:text-white" data-testid="mb-custom-result-close"><X size={16} /></button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="relative w-full overflow-auto rounded-lg border border-slate-800" data-testid="mb-custom-result-table-wrapper">
              <Table>
                <TableHeader className="bg-slate-900">
                  <TableRow>
                    <TableHead>Stock</TableHead><TableHead>Sector</TableHead><TableHead>RSI</TableHead><TableHead>GTT Buy</TableHead><TableHead>Type</TableHead>
                    <TableHead>1W</TableHead><TableHead>1M</TableHead><TableHead>3M</TableHead><TableHead>6M</TableHead><TableHead>9M</TableHead><TableHead>1Y</TableHead><TableHead>Score</TableHead>
                  </TableRow>
                </TableHeader>
                <MultibaggerCandidateCard
                  row={customMbResult}
                  expanded={true}
                  onToggleBands={() => {}}
                />
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}
