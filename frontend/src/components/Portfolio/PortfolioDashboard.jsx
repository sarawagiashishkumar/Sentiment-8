import { useState } from "react";
import axios from "axios";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PortfolioHoldingRow } from "./PortfolioHoldingRow";
import { PortfolioRiskPanel } from "./PortfolioRiskPanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function PortfolioDashboard({ authHeaders, syncCredits }) {
  const [portfolioFile, setPortfolioFile] = useState(null);
  const [portfolioRows, setPortfolioRows] = useState([{ symbol: "", avg_price: "", quantity: "" }]);
  const [portfolioData, setPortfolioData] = useState(null);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState("");

  const updatePortfolioRow = (index, field, value) => {
    setPortfolioRows((prev) => prev.map((row, idx) => (idx === index ? { ...row, [field]: value } : row)));
  };
  const addPortfolioRow = () => {
    setPortfolioRows((prev) => [...prev, { symbol: "", avg_price: "", quantity: "" }]);
  };
  const removePortfolioRow = (index) => {
    setPortfolioRows((prev) => { if (prev.length === 1) return prev; return prev.filter((_, idx) => idx !== index); });
  };

  const submitManualPortfolio = async (event) => {
    event.preventDefault();
    setPortfolioError("");
    const payloadRows = portfolioRows
      .map((row) => ({ symbol: row.symbol.trim().toUpperCase(), avg_price: Number(row.avg_price), quantity: Number(row.quantity) }))
      .filter((row) => row.symbol && row.avg_price > 0 && row.quantity > 0);
    if (!payloadRows.length) { setPortfolioError("Please add at least one valid portfolio row."); return; }
    setPortfolioLoading(true);
    try {
      const response = await axios.post(`${API}/portfolio/analyze`, { positions: payloadRows }, { headers: authHeaders });
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
    if (!portfolioFile) { setPortfolioError("Please choose a portfolio file first."); return; }
    setPortfolioLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", portfolioFile);
      const response = await axios.post(`${API}/portfolio/analyze-upload`, formData, { headers: { ...authHeaders } });
      setPortfolioData(response.data);
      syncCredits(response.data.credits_remaining);
    } catch (error) {
      setPortfolioError(error?.response?.data?.detail || "Unable to parse uploaded file.");
    } finally {
      setPortfolioLoading(false);
    }
  };

  return (
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
            <Button type="button" onClick={submitUploadedPortfolio} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="portfolio-upload-submit">
              <FileUp size={16} /> Analyze Uploaded Portfolio (0.2 per parsed stock)
            </Button>
          </div>

          <form className="space-y-3" onSubmit={submitManualPortfolio} data-testid="portfolio-manual-form">
            <p className="text-sm text-slate-200">Manual Portfolio Entry</p>
            {portfolioRows.map((row, index) => (
              <PortfolioHoldingRow key={`portfolio-row-${index}`} row={row} index={index} onUpdate={updatePortfolioRow} onAdd={addPortfolioRow} onRemove={removePortfolioRow} />
            ))}
            <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="portfolio-manual-submit">
              Submit Portfolio (0.2 per stock)
            </Button>
          </form>
        </CardContent>
      </Card>

      {portfolioError ? <p className="text-sm text-rose-400" data-testid="portfolio-error">{portfolioError}</p> : null}
      {portfolioLoading ? <p className="text-sm text-cyan-300" data-testid="portfolio-loading">Analyzing portfolio...</p> : null}
      {portfolioData ? (
        <p className="text-xs text-slate-300" data-testid="portfolio-charge-info">
          Charged: {portfolioData.cost_charged} | Credits Remaining: {portfolioData.credits_remaining}
        </p>
      ) : null}

      {portfolioData?.failed_symbols?.length > 0 && (
        <div className="flex flex-wrap gap-2 rounded-md border border-yellow-800 bg-yellow-900/20 p-3" data-testid="portfolio-failed-symbols-banner">
          <span className="text-xs font-semibold text-yellow-400">Live data temporarily unavailable:</span>
          {portfolioData.failed_symbols.map((sym) => (
            <span key={sym} className="rounded-full bg-yellow-900/50 px-2 py-0.5 text-xs font-mono text-yellow-300 border border-yellow-700" data-testid={`portfolio-failed-badge-${sym.toLowerCase()}`}>{sym}</span>
          ))}
          <span className="text-xs text-yellow-500">(remaining symbols analysed normally)</span>
        </div>
      )}

      <PortfolioRiskPanel portfolioData={portfolioData} />
    </section>
  );
}
