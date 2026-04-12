import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Eye, Plus, Trash2, Bell, RefreshCw } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function WatchlistPanel({ authHeaders }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [addForm, setAddForm] = useState({ symbol: "", alert_above: "", alert_below: "", notes: "" });
  const [showAddForm, setShowAddForm] = useState(false);

  const fetchWatchlist = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/watchlist`, { headers: authHeaders });
      setItems(res.data.items || []);
    } catch (err) {
      console.error("Watchlist fetch failed:", err?.message);
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => { fetchWatchlist(); }, [fetchWatchlist]);

  const handleAdd = async (e) => {
    e.preventDefault();
    const sym = addForm.symbol.trim().toUpperCase();
    if (!sym) return;
    try {
      await axios.post(`${API}/watchlist`, {
        symbol: sym,
        alert_above: addForm.alert_above ? Number(addForm.alert_above) : null,
        alert_below: addForm.alert_below ? Number(addForm.alert_below) : null,
        notes: addForm.notes || null,
      }, { headers: authHeaders });
      setAddForm({ symbol: "", alert_above: "", alert_below: "", notes: "" });
      setShowAddForm(false);
      await fetchWatchlist();
    } catch (err) {
      console.error("Watchlist add failed:", err?.message);
    }
  };

  const handleRemove = async (symbol) => {
    try {
      await axios.delete(`${API}/watchlist/${symbol}`, { headers: authHeaders });
      await fetchWatchlist();
    } catch (err) {
      console.error("Watchlist remove failed:", err?.message);
    }
  };

  return (
    <Card className="border-slate-800 bg-slate-950/70" data-testid="watchlist-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-white flex items-center gap-2">
          <Eye size={16} className="text-cyan-400" /> Watchlist
        </CardTitle>
        <div className="flex gap-2">
          <Button onClick={() => setShowAddForm(!showAddForm)} className="h-7 bg-cyan-600 text-white hover:bg-cyan-500 text-xs px-3" data-testid="watchlist-add-btn">
            <Plus size={12} className="mr-1" /> Add Symbol
          </Button>
          <Button onClick={fetchWatchlist} disabled={loading} className="h-7 bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs px-2" data-testid="watchlist-refresh">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Add form */}
        {showAddForm && (
          <form onSubmit={handleAdd} className="grid grid-cols-2 sm:grid-cols-5 gap-2 rounded-lg border border-slate-700 bg-slate-900/50 p-3" data-testid="watchlist-add-form">
            <Input value={addForm.symbol} onChange={(e) => setAddForm(p => ({ ...p, symbol: e.target.value.toUpperCase() }))} placeholder="Symbol (e.g. RELIANCE)" className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="watchlist-input-symbol" />
            <Input type="number" value={addForm.alert_above} onChange={(e) => setAddForm(p => ({ ...p, alert_above: e.target.value }))} placeholder="Alert Above" className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="watchlist-input-above" />
            <Input type="number" value={addForm.alert_below} onChange={(e) => setAddForm(p => ({ ...p, alert_below: e.target.value }))} placeholder="Alert Below" className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="watchlist-input-below" />
            <Input value={addForm.notes} onChange={(e) => setAddForm(p => ({ ...p, notes: e.target.value }))} placeholder="Notes" className="border-slate-700 bg-slate-800 text-slate-100 text-xs" data-testid="watchlist-input-notes" />
            <Button type="submit" className="h-8 bg-emerald-600 text-white hover:bg-emerald-500 text-xs" data-testid="watchlist-submit">Save</Button>
          </form>
        )}

        {/* Watchlist items */}
        {items.length > 0 ? (
          <div className="space-y-1.5" data-testid="watchlist-items">
            {items.map(item => (
              <div key={item.symbol} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2" data-testid={`watchlist-item-${item.symbol.toLowerCase()}`}>
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-xs text-white">{item.symbol}</span>
                  {item.alert_above && (
                    <span className="flex items-center gap-0.5 text-[10px] text-emerald-400">
                      <Bell size={9} /> Above {item.alert_above}
                    </span>
                  )}
                  {item.alert_below && (
                    <span className="flex items-center gap-0.5 text-[10px] text-rose-400">
                      <Bell size={9} /> Below {item.alert_below}
                    </span>
                  )}
                  {item.notes && <span className="text-[10px] text-slate-500 truncate max-w-[120px]">{item.notes}</span>}
                  {item.last_triggered && <span className="text-[9px] text-amber-400">Triggered</span>}
                </div>
                <button onClick={() => handleRemove(item.symbol)} className="text-slate-600 hover:text-rose-400 p-1" data-testid={`watchlist-remove-${item.symbol.toLowerCase()}`}>
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        ) : !loading ? (
          <div className="text-center py-4" data-testid="watchlist-empty">
            <Eye size={24} className="mx-auto text-slate-700 mb-1" />
            <p className="text-xs text-slate-500">No symbols in watchlist</p>
            <p className="text-[10px] text-slate-600 mt-0.5">Add symbols with price alerts to get notified during market hours</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
