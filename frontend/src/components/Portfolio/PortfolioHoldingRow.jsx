import { Minus, Plus } from "lucide-react";
import { Button } from "components/ui/button";
import { Input } from "components/ui/input";

export function PortfolioHoldingRow({ row, index, onUpdate, onAdd, onRemove }) {
  return (
    <div className="grid grid-cols-12 gap-2" data-testid={`portfolio-manual-row-${index}`}>
      <Input
        value={row.symbol}
        onChange={(event) => onUpdate(index, "symbol", event.target.value.toUpperCase())}
        placeholder="Symbol"
        className="col-span-4 border-slate-700 bg-slate-900 text-slate-100"
        data-testid={`portfolio-row-symbol-${index}`}
      />
      <Input
        type="number" min="0" step="0.01"
        value={row.avg_price}
        onChange={(event) => onUpdate(index, "avg_price", event.target.value)}
        placeholder="Avg Price"
        className="col-span-3 border-slate-700 bg-slate-900 text-slate-100"
        data-testid={`portfolio-row-avg-${index}`}
      />
      <Input
        type="number" min="0" step="0.01"
        value={row.quantity}
        onChange={(event) => onUpdate(index, "quantity", event.target.value)}
        placeholder="Qty"
        className="col-span-3 border-slate-700 bg-slate-900 text-slate-100"
        data-testid={`portfolio-row-qty-${index}`}
      />
      <div className="col-span-2 flex gap-1">
        <Button type="button" onClick={onAdd} className="h-10 w-10 bg-cyan-500 p-0 text-slate-900 hover:bg-cyan-400" data-testid={`portfolio-row-add-${index}`}>
          <Plus size={14} />
        </Button>
        <Button type="button" onClick={() => onRemove(index)} className="h-10 w-10 border border-rose-600 bg-transparent p-0 text-rose-300 hover:bg-rose-500/20" data-testid={`portfolio-row-remove-${index}`}>
          <Minus size={14} />
        </Button>
      </div>
    </div>
  );
}
