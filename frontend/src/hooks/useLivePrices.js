import { useState, useEffect, useRef, useCallback } from "react";

const WS_BASE = process.env.REACT_APP_BACKEND_URL?.replace("https://", "wss://").replace("http://", "ws://");

/**
 * Hook to stream live prices via WebSocket for watchlist symbols.
 * Auto-connects, sends symbol list, receives live quotes every 5s.
 */
export function useLivePrices(symbols = [], enabled = true) {
  const [quotes, setQuotes] = useState({});
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const symbolsRef = useRef(symbols);
  symbolsRef.current = symbols;

  const connect = useCallback(() => {
    if (!enabled || !WS_BASE || symbols.length === 0) return;

    try {
      const ws = new WebSocket(`${WS_BASE}/api/ws/prices`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        // Send initial symbols
        ws.send(JSON.stringify({ symbols: symbolsRef.current }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.quotes) {
            setQuotes(data.quotes);
          }
        } catch (err) {
          console.error("WS parse error:", err?.message);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        // Auto-reconnect after 5s
        if (enabled) {
          setTimeout(() => connect(), 5000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (err) {
      console.error("WS connect error:", err?.message);
    }
  }, [enabled, symbols.length]);

  // Connect on mount / symbol change
  useEffect(() => {
    if (!enabled || symbols.length === 0) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, enabled, symbols.length]);

  // Send updated symbols when list changes
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN && symbols.length > 0) {
      wsRef.current.send(JSON.stringify({ symbols }));
    }
  }, [symbols]);

  return { quotes, connected };
}
