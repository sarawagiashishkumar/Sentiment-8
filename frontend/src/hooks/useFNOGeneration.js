import { useState, useRef, useCallback, useEffect } from "react";
import axios from "axios";
import { readNDJSONStream } from "components/Shared/NDJSONStreamConsumer";

const API = "/api";

/**
 * Custom hook: encapsulates all FNO signal generation logic.
 * Isolates live data fetching from UI to prevent re-render storms.
 */
export function useFNOGeneration({ authHeaders, syncCredits }) {
  const [fnoData, setFnoData] = useState(null);
  const [fnoLoading, setFnoLoading] = useState(false);
  const [fnoError, setFnoError] = useState("");
  const [fnoProgress, setFnoProgress] = useState("");
  const abortRef = useRef(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => { if (abortRef.current) abortRef.current.abort(); };
  }, []);

  const generate = useCallback(async (script = "") => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setFnoError("");
    setFnoLoading(true);
    setFnoProgress("");
    try {
      const payload = script ? { custom_script: script.trim().toUpperCase() } : {};
      const response = await fetch(`${API}/fno/generate`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }
      const data = await readNDJSONStream(
        response,
        (evt) => setFnoProgress(evt.message || ""),
        controller.signal,
        (evt) => {
          if (!evt.data) return;
          setFnoData((prev) => {
            const merged = prev ? { ...prev } : {};
            if (evt.phase === "nifty" && evt.data.nifty_projection) {
              merged.nifty_projection = evt.data.nifty_projection;
              merged.signals = evt.data.nifty_projection.assured_signals || [];
              merged.potential_signals = merged.signals.filter(s => s.is_potential_trade);
              merged.top_trades = merged.potential_signals.slice(0, 4);
            }
            if (evt.phase === "banknifty" && evt.data.banknifty_projection) {
              merged.banknifty_projection = evt.data.banknifty_projection;
              const niftySigs = merged.nifty_projection?.assured_signals || [];
              const bnSigs = evt.data.banknifty_projection.assured_signals || [];
              merged.signals = [...niftySigs, ...bnSigs].sort((a, b) => (b.confluence_score || 0) - (a.confluence_score || 0));
              merged.potential_signals = merged.signals.filter(s => s.is_potential_trade);
              merged.top_trades = merged.potential_signals.slice(0, 4);
            }
            return merged;
          });
        },
      );
      if (data) {
        setFnoData(data);
        syncCredits(data.credits_remaining);
      }
    } catch (error) {
      if (error.name === "AbortError") return;
      setFnoError(error?.message || "Unable to generate F&O projections");
    } finally {
      setFnoLoading(false);
      setFnoProgress("");
    }
  }, [authHeaders, syncCredits]);

  return { fnoData, fnoLoading, fnoError, fnoProgress, generate };
}
