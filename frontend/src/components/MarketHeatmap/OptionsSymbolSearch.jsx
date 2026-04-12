import { useState, useRef } from "react";
import { Search, X } from "lucide-react";

const KNOWN_FNO_SYMBOLS = [
  "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT",
  "AXISBANK", "KOTAKBANK", "BAJFINANCE", "WIPRO", "HINDUNILVR", "BHARTIARTL",
  "TATAMOTORS", "MARUTI", "M&M", "SUNPHARMA", "TITAN", "ADANIPORTS",
  "TATASTEEL", "JSWSTEEL", "COALINDIA", "NTPC", "POWERGRID", "ONGC",
  "HCLTECH", "TECHM", "ULTRACEMCO", "NESTLEIND", "CIPLA", "DRREDDY",
  "DIVISLAB", "APOLLOHOSP", "HEROMOTOCO", "EICHERMOT", "BPCL", "TRENT",
  "HINDALCO", "SHRIRAMFIN", "DLF", "INDIGO", "HAL", "BEL", "ZOMATO",
  "PAYTM", "LIC", "DMART", "TATAPOWER", "VEDL",
];

export function OptionsSymbolSearch({ activeSymbol, setActiveSymbol }) {
  const [customStock, setCustomStock] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const timeoutRef = useRef(null);

  const handleInput = (value) => {
    setCustomStock(value);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    const q = value.trim().toUpperCase();
    if (q.length >= 2) {
      const matches = KNOWN_FNO_SYMBOLS.filter(s => s.includes(q)).slice(0, 5);
      setSuggestions(matches);
      if (matches.length === 1 && matches[0] === q) {
        timeoutRef.current = setTimeout(() => {
          setActiveSymbol(q);
          setCustomStock("");
          setSuggestions([]);
        }, 300);
      }
    } else {
      setSuggestions([]);
    }
  };

  const selectSuggestion = (sym) => {
    setActiveSymbol(sym);
    setCustomStock("");
    setSuggestions([]);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const sym = customStock.trim().toUpperCase();
    if (sym) { setActiveSymbol(sym); setCustomStock(""); setSuggestions([]); }
  };

  return (
    <div className="relative" data-testid="options-custom-search">
      <form onSubmit={handleSubmit} className="flex items-center gap-1">
        <div className="relative">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={customStock}
            onChange={(e) => handleInput(e.target.value)}
            placeholder="Search F&O symbol..."
            className="bg-slate-900 border border-slate-700 rounded-md pl-6 pr-6 py-1 text-xs text-slate-200 w-40 focus:border-cyan-500 focus:outline-none"
            data-testid="options-custom-stock-input"
          />
          {customStock && (
            <button type="button" onClick={() => { setCustomStock(""); setSuggestions([]); }} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
              <X size={11} />
            </button>
          )}
        </div>
      </form>
      {suggestions.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-40 bg-slate-900 border border-slate-700 rounded-md shadow-xl z-20" data-testid="options-search-suggestions">
          {suggestions.map(sym => (
            <button
              key={sym}
              onClick={() => selectSuggestion(sym)}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 font-mono"
              data-testid={`options-suggest-${sym.toLowerCase()}`}
            >
              {sym}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
