import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function AdminCsvTab({ csvSeeds, csvSeedLoading, csvSeedMsg, csvUploadSymbol, setCsvUploadSymbol, loadCsvSeeds, uploadCsvSeed, deleteCsvSeed }) {
  return (
    <Card className="result-card border-slate-800 bg-slate-950/70" data-testid="csv-seed-card">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white">OHLCV CSV Seed Management</CardTitle>
        <Button type="button" onClick={loadCsvSeeds} className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" data-testid="csv-seed-refresh-btn">Refresh Seeds</Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200" data-testid="csv-seed-guide">
          <p className="font-semibold mb-1">Admin Guide: CSV Seed Files</p>
          <ul className="list-disc pl-4 space-y-0.5">
            <li>Upload verified CSV files with columns: <code className="bg-slate-800 px-1 rounded">date,open,high,low,close,volume</code></li>
            <li>Files are named by symbol (e.g., NIFTY.csv, RELIANCE.csv)</li>
            <li>Used ONLY when Market Data API is unavailable (offline fallback)</li>
            <li>Data must be manually verified before upload — no auto-scraping</li>
            <li>Primary source is always Market Data API Historical Data</li>
          </ul>
        </div>
        <form onSubmit={uploadCsvSeed} className="grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="csv-seed-upload-form">
          <Input value={csvUploadSymbol} onChange={(e) => setCsvUploadSymbol(e.target.value)} placeholder="Symbol (e.g., NIFTY)" className="border-slate-700 bg-slate-900 text-slate-100" data-testid="csv-seed-symbol-input" />
          <input type="file" accept=".csv" className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-cyan-500/20 file:px-2 file:py-1 file:text-xs file:text-cyan-300" data-testid="csv-seed-file-input" />
          <Button type="submit" className="bg-cyan-500 text-slate-900 hover:bg-cyan-400" disabled={csvSeedLoading} data-testid="csv-seed-upload-btn">Upload CSV</Button>
        </form>
        {csvSeedMsg ? <p className="text-sm text-cyan-300" data-testid="csv-seed-msg">{csvSeedMsg}</p> : null}
        {csvSeedLoading ? (
          <p className="text-sm text-slate-400">Loading...</p>
        ) : csvSeeds.length > 0 ? (
          <div className="relative w-full overflow-auto rounded-lg border border-slate-800">
            <Table data-testid="csv-seed-table">
              <TableHeader>
                <TableRow className="border-slate-800 hover:bg-slate-900/50">
                  <TableHead className="text-slate-400">Symbol</TableHead><TableHead className="text-slate-400">File</TableHead><TableHead className="text-right text-slate-400">Rows</TableHead><TableHead className="text-right text-slate-400">Size (KB)</TableHead><TableHead className="text-right text-slate-400">Actions</TableHead>
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
                      <Button type="button" onClick={() => deleteCsvSeed(seed.symbol)} className="bg-rose-500/20 text-rose-300 hover:bg-rose-500/40 text-xs h-7 px-2" data-testid={`csv-seed-delete-${seed.symbol}`}>Delete</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-sm text-slate-500" data-testid="csv-seed-empty">No CSV seeds uploaded. Backtests will use Market Data API only.</p>
        )}
      </CardContent>
    </Card>
  );
}
