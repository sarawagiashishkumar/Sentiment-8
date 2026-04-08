import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/utils/formatters";

export function PortfolioRiskPanel({ portfolioData }) {
  if (!portfolioData?.stocks?.length) return null;
  return (
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
                        {values.min_expected_price != null ? `₹${formatNumber(values.min_expected_price)}` : "\u2014"}
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
  );
}
