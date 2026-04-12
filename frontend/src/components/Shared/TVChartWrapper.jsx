import { useEffect, useRef, useCallback } from "react";
import { createChart, ColorType } from "lightweight-charts";

/**
 * Reusable TradingView Lightweight Chart wrapper.
 * Supports candlestick, line, area, and histogram series.
 */
export function TVChart({ data, type = "candlestick", height = 300, width = "100%", markers = [], options = {} }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#94a3b8", fontSize: 10 },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: "#334155", scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: "#334155", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height,
      ...options,
    });
    chartRef.current = chart;

    let series;
    if (type === "candlestick") {
      series = chart.addCandlestickSeries({
        upColor: "#10b981", downColor: "#ef4444", borderUpColor: "#10b981", borderDownColor: "#ef4444",
        wickUpColor: "#10b981", wickDownColor: "#ef4444",
      });
      series.setData(data);
    } else if (type === "area") {
      series = chart.addAreaSeries({
        topColor: "rgba(6, 182, 212, 0.3)", bottomColor: "rgba(6, 182, 212, 0.02)",
        lineColor: "rgb(6, 182, 212)", lineWidth: 2,
      });
      series.setData(data);
    } else if (type === "line") {
      series = chart.addLineSeries({ color: "rgb(6, 182, 212)", lineWidth: 2 });
      series.setData(data);
    } else if (type === "histogram") {
      series = chart.addHistogramSeries({ color: "rgba(6, 182, 212, 0.5)" });
      series.setData(data);
    }

    if (markers.length > 0 && series) {
      series.setMarkers(markers);
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data, type, height, markers, options]);

  return <div ref={containerRef} style={{ width }} data-testid="tv-chart" />;
}

/**
 * Multi-series area chart for IV Cone (percentile bands).
 */
export function IVConeChart({ coneData, height = 280 }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !coneData?.bands || coneData.bands.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#94a3b8", fontSize: 10 },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155" },
      width: containerRef.current.clientWidth,
      height,
    });

    // P95 band (top)
    if (coneData.bands.some(b => b.p95 != null)) {
      const p95 = chart.addAreaSeries({
        topColor: "rgba(239, 68, 68, 0.08)", bottomColor: "rgba(239, 68, 68, 0.02)",
        lineColor: "rgba(239, 68, 68, 0.4)", lineWidth: 1,
      });
      p95.setData(coneData.bands.filter(b => b.p95 != null).map(b => ({ time: b.date, value: b.p95 })));
    }

    // P75 band
    if (coneData.bands.some(b => b.p75 != null)) {
      const p75 = chart.addAreaSeries({
        topColor: "rgba(251, 146, 60, 0.08)", bottomColor: "rgba(251, 146, 60, 0.02)",
        lineColor: "rgba(251, 146, 60, 0.4)", lineWidth: 1,
      });
      p75.setData(coneData.bands.filter(b => b.p75 != null).map(b => ({ time: b.date, value: b.p75 })));
    }

    // Current IV (main line)
    if (coneData.bands.some(b => b.current != null)) {
      const current = chart.addLineSeries({ color: "rgb(6, 182, 212)", lineWidth: 2 });
      current.setData(coneData.bands.filter(b => b.current != null).map(b => ({ time: b.date, value: b.current })));
    }

    // P25 band
    if (coneData.bands.some(b => b.p25 != null)) {
      const p25 = chart.addAreaSeries({
        topColor: "rgba(16, 185, 129, 0.02)", bottomColor: "rgba(16, 185, 129, 0.08)",
        lineColor: "rgba(16, 185, 129, 0.4)", lineWidth: 1,
      });
      p25.setData(coneData.bands.filter(b => b.p25 != null).map(b => ({ time: b.date, value: b.p25 })));
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);
    return () => { window.removeEventListener("resize", handleResize); chart.remove(); };
  }, [coneData, height]);

  if (!coneData?.bands || coneData.bands.length === 0) return null;
  return <div ref={containerRef} data-testid="iv-cone-chart" />;
}
