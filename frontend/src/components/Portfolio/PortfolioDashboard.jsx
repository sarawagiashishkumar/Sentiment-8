import { useState, useRef, useCallback } from "react";
import axios from "axios";
import { FileUp, Upload, X, File } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PortfolioHoldingRow } from "./PortfolioHoldingRow";
import { PortfolioRiskPanel } from "./PortfolioRiskPanel";
import { RiskDashboard } from "./RiskDashboard";

const API = "/api";
const ACCEPTED_TYPES = ".txt,.csv,.CSV,text/csv,application/csv,application/vnd.ms-excel,.xls,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.pdf,application/pdf,.jpg,.jpeg,.bmp,.png,.webp,image/*";

export function PortfolioDashboard({ authHeaders, syncCredits }) {
  const [portfolioFiles, setPortfolioFiles] = useState([]);
  const [portfolioRows, setPortfolioRows] = useState([{ symbol: "", avg_price: "", quantity: "" }]);
  const [portfolioData, setPortfolioData] = useState(null);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const updatePortfolioRow = (index, field, value) => {
    setPortfolioRows((prev) => prev.map((row, idx) => (idx === index ? { ...row, [field]: value } : row)));
  };
  const addPortfolioRow = () => {
    setPortfolioRows((prev) => [...prev, { symbol: "", avg_price: "", quantity: "" }]);
  };
  const removePortfolioRow = (index) => {
    setPortfolioRows((prev) => { if (prev.length === 1) return prev; return prev.filter((_, idx) => idx !== index); });
  };

  const addFiles = useCallback((newFiles) => {
    const fileList = Array.from(newFiles);
    setPortfolioFiles(prev => [...prev, ...fileList]);
    setPortfolioError("");
  }, []);

  const removeFile = (index) => {
    setPortfolioFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Drag and drop handlers
  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files?.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }, [addFiles]);

  const handleFileInputChange = (e) => {
    if (e.target.files?.length > 0) {
      addFiles(e.target.files);
    }
    // Reset input so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = "";
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
    if (portfolioFiles.length === 0) { setPortfolioError("Please add at least one portfolio file."); return; }
    setPortfolioLoading(true);
    try {
      const formData = new FormData();
      // Support multiple files
      portfolioFiles.forEach((file, idx) => {
        formData.append("files", file);
      });
      // Also append first file as "file" for backwards compatibility
      formData.append("file", portfolioFiles[0]);

      const response = await axios.post(`${API}/portfolio/analyze-upload`, formData, { headers: { ...authHeaders } });
      setPortfolioData(response.data);
      syncCredits(response.data.credits_remaining);
      setPortfolioFiles([]); // Clear on success
    } catch (error) {
      setPortfolioError(error?.response?.data?.detail || "Unable to parse uploaded file(s).");
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
          {/* File Upload with Drag & Drop */}
          <div className="space-y-3">
            <p className="text-sm text-slate-200">Upload Portfolio Files (.txt, .csv, .xls, .xlsx, .pdf, .jpg, .jpeg, .bmp, .png, .webp)</p>

            {/* Drag-and-Drop Zone */}
            <div
              data-testid="portfolio-drop-zone"
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 cursor-pointer transition-all ${
                isDragging
                  ? "border-cyan-400 bg-cyan-500/10 scale-[1.01]"
                  : "border-slate-700 bg-slate-900/50 hover:border-slate-500"
              }`}
            >
              <Upload size={28} className={`mb-2 ${isDragging ? "text-cyan-400" : "text-slate-500"}`} />
              <p className={`text-xs ${isDragging ? "text-cyan-300" : "text-slate-400"}`}>
                {isDragging ? "Drop files here..." : "Drag & drop files here, or click to browse"}
              </p>
              <p className="text-[10px] text-slate-500 mt-1">Supports multiple files simultaneously</p>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_TYPES}
                multiple
                onChange={handleFileInputChange}
                className="hidden"
                data-testid="portfolio-file-input"
              />
            </div>

            {/* File list */}
            {portfolioFiles.length > 0 && (
              <div className="space-y-1.5" data-testid="portfolio-file-list">
                {portfolioFiles.map((file, idx) => (
                  <div key={`${file.name}-${idx}`} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-1.5">
                    <div className="flex items-center gap-2">
                      <File size={13} className="text-cyan-400" />
                      <span className="text-xs text-slate-300 truncate max-w-[200px]">{file.name}</span>
                      <span className="text-[10px] text-slate-500">({(file.size / 1024).toFixed(1)} KB)</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFile(idx); }}
                      className="text-slate-500 hover:text-rose-400 p-0.5"
                      data-testid={`portfolio-remove-file-${idx}`}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <Button
              type="button"
              onClick={submitUploadedPortfolio}
              className="bg-cyan-500 text-slate-900 hover:bg-cyan-400"
              data-testid="portfolio-upload-submit"
              disabled={portfolioFiles.length === 0 || portfolioLoading}
            >
              <FileUp size={16} /> Analyze {portfolioFiles.length > 1 ? `${portfolioFiles.length} Files` : "Uploaded Portfolio"} (0.2 per parsed stock)
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

      <RiskDashboard authHeaders={authHeaders} />
    </section>
  );
}
