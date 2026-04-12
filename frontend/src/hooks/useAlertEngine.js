import { useRef, useEffect, useCallback } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const URGENT_ALERTS = new Set(["EXIT_URGENT_TIME", "EXIT_URGENT_LOSS", "RISKY_PREMIUM", "EXIT_NOW_HIGH_LOSS", "EXIT_URGENT_NO_RECOVERY"]);
const WARNING_ALERTS = new Set(["EXIT_PREMIUM_DECAY", "APPROACHING_SL", "LOSS_WARNING"]);
const TARGET_STATES = new Set(["WATCHING_T1", "WATCHING_T2", "CLOSED_WIN"]);

export function useAlertEngine({ customPositions, alertSoundEnabled, authHeaders, addNotification, sendPush }) {
  const audioContextRef = useRef(null);
  const urgentBuzzedRef = useRef(new Set());
  const targetBuzzedRef = useRef(new Set());
  const warningBuzzedRef = useRef(new Set());

  const playAlertSound = useCallback((type = "urgent") => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioContextRef.current || audioContextRef.current.state === "closed") {
        audioContextRef.current = new AudioCtx();
      }
      const ctx = audioContextRef.current;
      if (ctx.state === "suspended") ctx.resume();

      const scheduleBeep = (freq, startAt, duration, gainPeak = 0.55, waveType = "square") => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = waveType;
        osc.frequency.setValueAtTime(freq, startAt);
        gain.gain.setValueAtTime(0.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(gainPeak, startAt + 0.04);
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startAt);
        osc.stop(startAt + duration + 0.01);
      };

      const now = ctx.currentTime;
      if (type === "urgent") {
        scheduleBeep(1100, now, 0.28, 0.65, "square");
        scheduleBeep(900, now + 0.32, 0.28, 0.65, "square");
        scheduleBeep(1100, now + 0.64, 0.36, 0.70, "square");
      } else if (type === "target") {
        scheduleBeep(660, now, 0.30, 0.55, "sine");
        scheduleBeep(880, now + 0.35, 0.30, 0.55, "sine");
        scheduleBeep(1100, now + 0.70, 0.50, 0.60, "sine");
      } else if (type === "warning") {
        scheduleBeep(820, now, 0.35, 0.50, "triangle");
        scheduleBeep(820, now + 0.45, 0.35, 0.50, "triangle");
      }
    } catch { /* ignore autoplay restrictions */ }
  }, []);

  const enableAlertSound = useCallback(async () => {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error("Audio not supported");
    if (!audioContextRef.current || audioContextRef.current.state === "closed") {
      audioContextRef.current = new AudioCtx();
    }
    const ctx = audioContextRef.current;
    if (ctx.state === "suspended") await ctx.resume();
  }, []);

  // Alert monitor
  useEffect(() => {
    if (!Array.isArray(customPositions) || customPositions.length === 0) return;
    if (typeof window === "undefined" || document.hidden) return;
    if (!alertSoundEnabled) return;

    const freshUrgent = customPositions.filter(p => URGENT_ALERTS.has(p.alert) && !urgentBuzzedRef.current.has(p.id));
    if (freshUrgent.length > 0) {
      playAlertSound("urgent");
      freshUrgent.forEach(p => {
        urgentBuzzedRef.current.add(p.id);
        addNotification("critical", p.alert.replace(/_/g, " "), `${p.symbol || "Position"}: ${p.alert}`, { symbol: p.symbol });
        sendPush(`CRITICAL: ${p.alert.replace(/_/g, " ")}`, `${p.symbol || "Position"}: ${p.alert}`, "critical");
      });
    }

    const freshTargets = customPositions.filter(p => TARGET_STATES.has(p.signal_state) && !targetBuzzedRef.current.has(`${p.id}_${p.signal_state}`));
    if (freshTargets.length > 0) {
      playAlertSound("target");
      freshTargets.forEach(p => {
        targetBuzzedRef.current.add(`${p.id}_${p.signal_state}`);
        addNotification("success", p.signal_state.replace(/_/g, " "), `${p.symbol || "Position"}: ${p.signal_state}`, { symbol: p.symbol });
      });
    }

    const freshWarnings = customPositions.filter(p => WARNING_ALERTS.has(p.alert) && !warningBuzzedRef.current.has(p.id));
    if (freshWarnings.length > 0 && freshUrgent.length === 0) {
      playAlertSound("warning");
      freshWarnings.forEach(p => {
        warningBuzzedRef.current.add(p.id);
        addNotification("warning", p.alert.replace(/_/g, " "), `${p.symbol || "Position"}: ${p.alert}`, { symbol: p.symbol });
        sendPush(`WARNING: ${p.alert.replace(/_/g, " ")}`, `${p.symbol || "Position"}: ${p.alert}`, "warning");
      });
    }

    // Persist
    if (freshUrgent.length > 0 || freshTargets.length > 0 || freshWarnings.length > 0) {
      const toSave = [
        ...freshUrgent.map(p => ({ category: "critical", title: p.alert.replace(/_/g, " "), message: `${p.symbol || "Position"}: ${p.alert}`, symbol: p.symbol })),
        ...freshTargets.map(p => ({ category: "success", title: p.signal_state.replace(/_/g, " "), message: `${p.symbol || "Position"}: ${p.signal_state}`, symbol: p.symbol })),
        ...freshWarnings.map(p => ({ category: "warning", title: p.alert.replace(/_/g, " "), message: `${p.symbol || "Position"}: ${p.alert}`, symbol: p.symbol })),
      ];
      axios.post(`${API}/notifications`, { notifications: toSave }, { headers: authHeaders }).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customPositions, alertSoundEnabled]);

  return { playAlertSound, enableAlertSound };
}
