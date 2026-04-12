import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MessageCircle, Phone, PhoneOff, Send, X, Bug, Minimize2, Maximize2 } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const WS_BASE = process.env.REACT_APP_BACKEND_URL?.replace("https://", "wss://").replace("http://", "ws://");

export function LiveHelpModule({ authHeaders, me }) {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [mode, setMode] = useState("text"); // "text" or "voice"
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [peerConnected, setPeerConnected] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [sessionId] = useState(() => `help-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`);

  const wsRef = useRef(null);
  const pcRef = useRef(null);
  const localStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const chatEndRef = useRef(null);
  const iceServersRef = useRef([]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Log session actions for analysis
  const logAction = useCallback(async (action) => {
    try {
      await axios.post(`${API}/livehelp/log-action`, action, { headers: authHeaders });
    } catch {}
  }, [authHeaders]);

  // Intercept axios for session logging
  useEffect(() => {
    if (!authHeaders?.Authorization) return;
    const id = axios.interceptors.response.use(
      (res) => {
        logAction({ action: "api_call", endpoint: res.config?.url?.replace(API, ""), status: String(res.status) });
        return res;
      },
      (err) => {
        logAction({ action: "api_error", endpoint: err.config?.url?.replace(API, ""), status: String(err.response?.status || "network"), error: err.response?.data?.detail || err.message });
        return Promise.reject(err);
      }
    );
    return () => axios.interceptors.response.eject(id);
  }, [authHeaders, logAction]);

  const connectWS = useCallback(() => {
    if (!WS_BASE || wsRef.current) return;
    const ws = new WebSocket(`${WS_BASE}/api/ws/livehelp/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ type: "join", role: "user", user_key: me?.user_key || "", username: me?.username || "User" }));
      setMessages(prev => [...prev, { type: "system", text: "Connected to Live Help. An admin will join when available.", ts: new Date().toISOString() }]);
      // Fetch session analysis hints on connect
      axios.get(`${API}/livehelp/session-analysis`, { headers: authHeaders }).then(res => {
        (res.data.suggestions || []).forEach(s => {
          setMessages(prev => [...prev, { type: "hint", text: s.message, severity: s.severity, ts: new Date().toISOString() }]);
        });
      }).catch(() => {});
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "chat") {
          setMessages(prev => [...prev, { type: "incoming", text: msg.text, sender: msg.sender, ts: msg.ts }]);
        } else if (msg.type === "system-hint") {
          setMessages(prev => [...prev, { type: "hint", text: msg.message, severity: msg.severity, ts: new Date().toISOString() }]);
        } else if (msg.type === "peer-joined") {
          setPeerConnected(true);
          setMessages(prev => [...prev, { type: "system", text: `${msg.username || "Admin"} joined the session.`, ts: new Date().toISOString() }]);
        } else if (msg.type === "peer-left") {
          setPeerConnected(false);
          setMessages(prev => [...prev, { type: "system", text: "Admin left the session.", ts: new Date().toISOString() }]);
        } else if (msg.type === "ice-servers") {
          iceServersRef.current = msg.servers || [];
        } else if (msg.type === "offer") {
          handleRemoteOffer(msg.sdp);
        } else if (msg.type === "answer") {
          handleRemoteAnswer(msg.sdp);
        } else if (msg.type === "ice-candidate" && msg.candidate) {
          handleRemoteIceCandidate(msg.candidate);
        } else if (msg.type === "voice-start") {
          setVoiceActive(true);
          setMode("voice");
        } else if (msg.type === "voice-end") {
          setVoiceActive(false);
          setMode("text");
        }
      } catch {}
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
    };
  }, [sessionId, me]);

  const disconnectWS = useCallback(() => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    setConnected(false);
    setPeerConnected(false);
    setVoiceActive(false);
  }, []);

  const sendChat = (e) => {
    e.preventDefault();
    if (!input.trim() || !wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: "chat", text: input.trim(), sender: me?.username || "User", user_key: me?.user_key || "" }));
    setMessages(prev => [...prev, { type: "outgoing", text: input.trim(), sender: me?.username || "You", ts: new Date().toISOString() }]);
    setInput("");
  };

  const reportBug = () => {
    if (!wsRef.current) return;
    const desc = window.prompt("Describe the issue briefly:");
    if (desc) {
      wsRef.current.send(JSON.stringify({ type: "report-bug", description: desc }));
      setMessages(prev => [...prev, { type: "system", text: "Bug report submitted. A ticket has been created for the admin.", ts: new Date().toISOString() }]);
    }
  };

  // ── WebRTC Voice ────────────────────────────────────────────────────
  const createPeerConnection = useCallback(() => {
    // Use fetched ICE servers, fallback to Google STUN
    const config = iceServersRef.current.length > 0 ? iceServersRef.current : [{ urls: "stun:stun.l.google.com:19302" }];
    const pc = new RTCPeerConnection({ iceServers: config });
    pc.onicecandidate = (e) => {
      if (e.candidate && wsRef.current) {
        wsRef.current.send(JSON.stringify({ type: "ice-candidate", candidate: e.candidate.toJSON() }));
      }
    };
    pc.ontrack = (e) => {
      if (remoteAudioRef.current && e.streams[0]) {
        remoteAudioRef.current.srcObject = e.streams[0];
      }
    };
    pcRef.current = pc;
    return pc;
  }, []);

  const startVoice = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStreamRef.current = stream;
      const pc = createPeerConnection();
      stream.getTracks().forEach(t => pc.addTrack(t, stream));
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(JSON.stringify({ type: "offer", sdp: pc.localDescription.toJSON() }));
      wsRef.current?.send(JSON.stringify({ type: "voice-start" }));
      setVoiceActive(true);
      setMode("voice");
    } catch (err) {
      setMessages(prev => [...prev, { type: "system", text: `Microphone access denied: ${err.message}`, ts: new Date().toISOString() }]);
    }
  };

  const stopVoice = () => {
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    wsRef.current?.send(JSON.stringify({ type: "voice-end" }));
    setVoiceActive(false);
    setMode("text");
  };

  const handleRemoteOffer = async (sdp) => {
    const pc = createPeerConnection();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStreamRef.current = stream;
      stream.getTracks().forEach(t => pc.addTrack(t, stream));
    } catch {}
    await pc.setRemoteDescription(new RTCSessionDescription(sdp));
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    wsRef.current?.send(JSON.stringify({ type: "answer", sdp: pc.localDescription.toJSON() }));
    setVoiceActive(true);
    setMode("voice");
  };

  const handleRemoteAnswer = async (sdp) => {
    if (pcRef.current) await pcRef.current.setRemoteDescription(new RTCSessionDescription(sdp));
  };

  const handleRemoteIceCandidate = async (candidate) => {
    if (pcRef.current) {
      try { await pcRef.current.addIceCandidate(new RTCIceCandidate(candidate)); } catch {}
    }
  };

  useEffect(() => { return () => disconnectWS(); }, [disconnectWS]);

  // ── Render ──────────────────────────────────────────────────────────
  if (!open) {
    return (
      <button onClick={() => { setOpen(true); connectWS(); }} className="fixed bottom-20 right-6 z-50 flex items-center gap-2 rounded-full bg-violet-600 px-4 py-3 text-white shadow-lg shadow-violet-600/30 hover:bg-violet-500 transition-all" data-testid="livehelp-fab">
        <MessageCircle size={18} /> <span className="text-xs font-semibold hidden sm:inline">Live Help</span>
      </button>
    );
  }

  if (minimized) {
    return (
      <div className="fixed bottom-20 right-6 z-50 flex items-center gap-2 rounded-full bg-violet-600 px-4 py-2 text-white shadow-lg cursor-pointer" onClick={() => setMinimized(false)} data-testid="livehelp-minimized">
        <MessageCircle size={14} />
        <span className="text-[10px] font-semibold">Live Help</span>
        {messages.filter(m => m.type === "incoming").length > 0 && <span className="bg-rose-500 text-[9px] rounded-full px-1">!</span>}
        <Maximize2 size={12} />
      </div>
    );
  }

  return (
    <div className="fixed bottom-20 right-6 z-50 w-80 sm:w-96 rounded-xl border border-violet-500/40 bg-slate-950 shadow-2xl shadow-violet-600/10 flex flex-col" style={{ maxHeight: "70vh" }} data-testid="livehelp-panel">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-xl bg-violet-600/20 border-b border-violet-500/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <MessageCircle size={14} className="text-violet-300" />
          <span className="text-xs font-bold text-white">Live Help</span>
          <span className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400" : "bg-slate-600"}`} />
          {voiceActive && <span className="text-[9px] text-emerald-400 animate-pulse">Voice Active</span>}
        </div>
        <div className="flex items-center gap-1">
          {connected && !voiceActive && <button onClick={startVoice} className="p-1 text-violet-300 hover:text-white" title="Start voice" data-testid="livehelp-voice-start"><Phone size={13} /></button>}
          {voiceActive && <button onClick={stopVoice} className="p-1 text-rose-400 hover:text-rose-300" title="End voice" data-testid="livehelp-voice-stop"><PhoneOff size={13} /></button>}
          <button onClick={reportBug} className="p-1 text-amber-400 hover:text-amber-300" title="Report bug" data-testid="livehelp-report-bug"><Bug size={13} /></button>
          <button onClick={() => setMinimized(true)} className="p-1 text-slate-400 hover:text-white"><Minimize2 size={13} /></button>
          <button onClick={() => { setOpen(false); disconnectWS(); }} className="p-1 text-slate-400 hover:text-white" data-testid="livehelp-close"><X size={13} /></button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5" style={{ minHeight: 200, maxHeight: "50vh" }}>
        {messages.map((msg, i) => (
          <div key={`msg-${i}`} className={`text-[11px] leading-relaxed ${
            msg.type === "system" ? "text-slate-500 italic text-center" :
            msg.type === "hint" ? `rounded-md px-2 py-1 ${msg.severity === "high" ? "bg-rose-950/40 text-rose-300 border border-rose-700/30" : "bg-amber-950/30 text-amber-300 border border-amber-700/30"}` :
            msg.type === "outgoing" ? "text-right" :
            msg.type === "incoming" ? "text-left" : ""
          }`}>
            {msg.type === "outgoing" && <div className="inline-block rounded-lg bg-violet-600/30 border border-violet-500/30 px-2.5 py-1.5 max-w-[80%]"><span className="text-violet-200">{msg.text}</span></div>}
            {msg.type === "incoming" && <div className="inline-block rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-1.5 max-w-[80%]"><span className="text-[9px] text-cyan-400 block mb-0.5">{msg.sender}</span><span className="text-slate-200">{msg.text}</span></div>}
            {msg.type === "hint" && <span>{msg.text}</span>}
            {msg.type === "system" && <span>{msg.text}</span>}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={sendChat} className="border-t border-violet-500/30 px-2 py-2 flex gap-1.5">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder={mode === "voice" ? "Voice active..." : "Type a message..."} disabled={mode === "voice"} className="flex-1 h-8 border-slate-700 bg-slate-900 text-slate-100 text-xs" data-testid="livehelp-input" />
        <Button type="submit" disabled={!input.trim() || mode === "voice"} className="h-8 w-8 p-0 bg-violet-600 hover:bg-violet-500" data-testid="livehelp-send"><Send size={13} /></Button>
      </form>

      <audio ref={remoteAudioRef} autoPlay hidden />
    </div>
  );
}
