import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MessageCircle, Phone, PhoneOff, Send, X, Bug, Minimize2, Maximize2, Monitor, MonitorOff, Mic, MicOff, Bot } from "lucide-react";
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
  const [screenSharing, setScreenSharing] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [sessionId] = useState(() => `help-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`);

  const wsRef = useRef(null);
  const pcRef = useRef(null);
  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const chatEndRef = useRef(null);
  const iceServersRef = useRef([]);
  const recognitionRef = useRef(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Log session actions for AI context
  const logAction = useCallback(async (action) => {
    try {
      await axios.post(`${API}/livehelp/log-action`, action, { headers: authHeaders });
    } catch {}
  }, [authHeaders]);

  // Axios interceptor for session logging
  useEffect(() => {
    if (!authHeaders?.Authorization) return;
    const id = axios.interceptors.response.use(
      (res) => { logAction({ action: "api_call", endpoint: res.config?.url?.replace(API, ""), status: String(res.status) }); return res; },
      (err) => { logAction({ action: "api_error", endpoint: err.config?.url?.replace(API, ""), status: String(err.response?.status || "network"), error: err.response?.data?.detail || err.message }); return Promise.reject(err); }
    );
    return () => axios.interceptors.response.eject(id);
  }, [authHeaders, logAction]);

  // ── AI Chat (primary interaction) ───────────────────────────────────
  const sendToAI = async (text) => {
    if (!text.trim()) return;
    setMessages(prev => [...prev, { type: "outgoing", text: text.trim(), sender: me?.username || "You", ts: new Date().toISOString() }]);
    setInput("");
    setAiLoading(true);

    try {
      const res = await axios.post(`${API}/livehelp/ai-chat`, {
        message: text.trim(),
        session_id: sessionId,
      }, { headers: authHeaders });

      const data = res.data;
      setMessages(prev => [...prev, {
        type: "ai",
        text: data.reply,
        sender: "AI Support",
        ts: new Date().toISOString(),
        autoTicket: data.auto_ticket,
      }]);

      if (data.auto_ticket) {
        setMessages(prev => [...prev, { type: "system", text: "A support ticket has been auto-created for the team.", ts: new Date().toISOString() }]);
      }
    } catch {
      setMessages(prev => [...prev, { type: "ai", text: "I'm having trouble connecting. Please try the Contact Support option in the dashboard.", sender: "AI Support", ts: new Date().toISOString() }]);
    }
    setAiLoading(false);
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendToAI(input);
  };

  // ── Speech-to-Text (Mic Button) ────────────────────────────────────
  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMessages(prev => [...prev, { type: "system", text: "Speech recognition not supported in this browser.", ts: new Date().toISOString() }]);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-IN";
    recognitionRef.current = recognition;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map(r => r[0].transcript).join("");
      if (event.results[0].isFinal) {
        sendToAI(transcript);
      } else {
        setInput(transcript);
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== "no-speech") {
        setMessages(prev => [...prev, { type: "system", text: `Mic error: ${event.error}`, ts: new Date().toISOString() }]);
      }
      setIsListening(false);
    };

    recognition.start();
  };

  // ── WebSocket for admin live chat ───────────────────────────────────
  const connectWS = useCallback(() => {
    if (!WS_BASE || wsRef.current) return;
    const ws = new WebSocket(`${WS_BASE}/api/ws/livehelp/${sessionId}`);
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ type: "join", role: "user", user_key: me?.user_key || "", username: me?.username || "User" }));
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
          setMessages(prev => [...prev, { type: "system", text: `${msg.username || "Admin"} joined. You're now in live support.`, ts: new Date().toISOString() }]);
        } else if (msg.type === "peer-left") {
          setPeerConnected(false);
          setMessages(prev => [...prev, { type: "system", text: "Admin left the session.", ts: new Date().toISOString() }]);
        } else if (msg.type === "ice-servers") {
          iceServersRef.current = msg.servers || [];
        } else if (msg.type === "offer") { handleRemoteOffer(msg.sdp); }
        else if (msg.type === "answer") { handleRemoteAnswer(msg.sdp); }
        else if (msg.type === "ice-candidate" && msg.candidate) { handleRemoteIceCandidate(msg.candidate); }
        else if (msg.type === "voice-start") { setVoiceActive(true); setMode("voice"); }
        else if (msg.type === "voice-end") { setVoiceActive(false); setMode("text"); }
      } catch {}
    };
    ws.onclose = () => { setConnected(false); wsRef.current = null; };
  }, [sessionId, me]);

  const disconnectWS = useCallback(() => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    if (screenStreamRef.current) { screenStreamRef.current.getTracks().forEach(t => t.stop()); screenStreamRef.current = null; }
    setConnected(false); setPeerConnected(false); setVoiceActive(false); setScreenSharing(false);
  }, []);

  const reportBug = () => {
    const desc = window.prompt("Describe the issue briefly:");
    if (desc) {
      sendToAI(`I want to report a bug: ${desc}`);
    }
  };

  // ── WebRTC ──────────────────────────────────────────────────────────
  const createPeerConnection = useCallback(() => {
    const config = iceServersRef.current.length > 0 ? iceServersRef.current : [{ urls: "stun:stun.l.google.com:19302" }];
    const pc = new RTCPeerConnection({ iceServers: config });
    pc.onicecandidate = (e) => { if (e.candidate && wsRef.current) wsRef.current.send(JSON.stringify({ type: "ice-candidate", candidate: e.candidate.toJSON() })); };
    pc.ontrack = (e) => {
      if (e.track.kind === "audio" && remoteAudioRef.current && e.streams[0]) remoteAudioRef.current.srcObject = e.streams[0];
      else if (e.track.kind === "video" && remoteVideoRef.current && e.streams[0]) remoteVideoRef.current.srcObject = e.streams[0];
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
      setVoiceActive(true); setMode("voice");
    } catch (err) { setMessages(prev => [...prev, { type: "system", text: `Mic access denied: ${err.message}`, ts: new Date().toISOString() }]); }
  };

  const stopVoice = () => {
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    wsRef.current?.send(JSON.stringify({ type: "voice-end" }));
    setVoiceActive(false); setMode("text");
  };

  const startScreenShare = async () => {
    try {
      const screenStream = await navigator.mediaDevices.getDisplayMedia({ video: { cursor: "always" }, audio: false });
      screenStreamRef.current = screenStream;
      let pc = pcRef.current || createPeerConnection();
      screenStream.getTracks().forEach(t => { pc.addTrack(t, screenStream); t.onended = () => stopScreenShare(); });
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(JSON.stringify({ type: "offer", sdp: pc.localDescription.toJSON() }));
      wsRef.current?.send(JSON.stringify({ type: "screen-share-start" }));
      setScreenSharing(true);
    } catch (err) { if (err.name !== "NotAllowedError") setMessages(prev => [...prev, { type: "system", text: `Screen share failed: ${err.message}`, ts: new Date().toISOString() }]); }
  };

  const stopScreenShare = () => {
    if (screenStreamRef.current) { screenStreamRef.current.getTracks().forEach(t => t.stop()); screenStreamRef.current = null; }
    wsRef.current?.send(JSON.stringify({ type: "screen-share-end" }));
    setScreenSharing(false);
  };

  const handleRemoteOffer = async (sdp) => { const pc = createPeerConnection(); try { const s = await navigator.mediaDevices.getUserMedia({ audio: true }); localStreamRef.current = s; s.getTracks().forEach(t => pc.addTrack(t, s)); } catch {} await pc.setRemoteDescription(new RTCSessionDescription(sdp)); const ans = await pc.createAnswer(); await pc.setLocalDescription(ans); wsRef.current?.send(JSON.stringify({ type: "answer", sdp: pc.localDescription.toJSON() })); setVoiceActive(true); setMode("voice"); };
  const handleRemoteAnswer = async (sdp) => { if (pcRef.current) await pcRef.current.setRemoteDescription(new RTCSessionDescription(sdp)); };
  const handleRemoteIceCandidate = async (c) => { if (pcRef.current) { try { await pcRef.current.addIceCandidate(new RTCIceCandidate(c)); } catch {} } };

  useEffect(() => { return () => disconnectWS(); }, [disconnectWS]);

  // ── Welcome message on open ─────────────────────────────────────────
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{
        type: "ai",
        text: "Hi! I'm your AI Support Agent. Ask me anything about the platform — signals, heatmaps, portfolio analysis, or troubleshooting. You can also tap the mic button to speak.",
        sender: "AI Support",
        ts: new Date().toISOString(),
      }]);
      connectWS();
    }
  }, [open, messages.length, connectWS]);

  // ── Render ──────────────────────────────────────────────────────────
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="fixed bottom-20 right-6 z-50 flex items-center gap-2 rounded-full bg-violet-600 px-4 py-3 text-white shadow-lg shadow-violet-600/30 hover:bg-violet-500 transition-all" data-testid="livehelp-fab">
        <Bot size={18} /> <span className="text-xs font-semibold hidden sm:inline">AI Support</span>
      </button>
    );
  }

  if (minimized) {
    return (
      <div className="fixed bottom-20 right-6 z-50 flex items-center gap-2 rounded-full bg-violet-600 px-4 py-2 text-white shadow-lg cursor-pointer" onClick={() => setMinimized(false)} data-testid="livehelp-minimized">
        <Bot size={14} /> <span className="text-[10px] font-semibold">AI Support</span>
        <Maximize2 size={12} />
      </div>
    );
  }

  return (
    <div className="fixed bottom-20 right-6 z-50 w-80 sm:w-96 rounded-xl border border-violet-500/40 bg-slate-950 shadow-2xl shadow-violet-600/10 flex flex-col" style={{ maxHeight: "70vh" }} data-testid="livehelp-panel">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-xl bg-violet-600/20 border-b border-violet-500/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <Bot size={14} className="text-violet-300" />
          <span className="text-xs font-bold text-white">AI Support Agent</span>
          {connected && <span className="w-2 h-2 rounded-full bg-emerald-400" />}
          {voiceActive && <span className="text-[9px] text-emerald-400 animate-pulse">Voice</span>}
          {screenSharing && <span className="text-[9px] text-cyan-400 animate-pulse">Screen</span>}
        </div>
        <div className="flex items-center gap-1">
          {connected && peerConnected && !voiceActive && <button onClick={startVoice} className="p-1 text-violet-300 hover:text-white" title="Voice call" data-testid="livehelp-voice-start"><Phone size={13} /></button>}
          {voiceActive && <button onClick={stopVoice} className="p-1 text-rose-400 hover:text-rose-300" title="End voice" data-testid="livehelp-voice-stop"><PhoneOff size={13} /></button>}
          {connected && peerConnected && !screenSharing && <button onClick={startScreenShare} className="p-1 text-cyan-300 hover:text-white" title="Share screen" data-testid="livehelp-screen-start"><Monitor size={13} /></button>}
          {screenSharing && <button onClick={stopScreenShare} className="p-1 text-rose-400" title="Stop share" data-testid="livehelp-screen-stop"><MonitorOff size={13} /></button>}
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
            msg.type === "ai" ? "text-left" :
            msg.type === "incoming" ? "text-left" : ""
          }`}>
            {msg.type === "outgoing" && <div className="inline-block rounded-lg bg-violet-600/30 border border-violet-500/30 px-2.5 py-1.5 max-w-[85%]"><span className="text-violet-200">{msg.text}</span></div>}
            {msg.type === "ai" && (
              <div className="inline-block rounded-lg bg-slate-800/80 border border-slate-700 px-2.5 py-1.5 max-w-[85%]">
                <span className="text-[9px] text-violet-400 block mb-0.5 flex items-center gap-1"><Bot size={9} /> AI Support</span>
                <span className="text-slate-200">{msg.text}</span>
                {msg.autoTicket && <span className="text-[9px] text-amber-400 block mt-1">Support ticket created</span>}
              </div>
            )}
            {msg.type === "incoming" && <div className="inline-block rounded-lg bg-cyan-900/30 border border-cyan-700/30 px-2.5 py-1.5 max-w-[85%]"><span className="text-[9px] text-cyan-400 block mb-0.5">{msg.sender} (Admin)</span><span className="text-slate-200">{msg.text}</span></div>}
            {msg.type === "hint" && <span>{msg.text}</span>}
            {msg.type === "system" && <span>{msg.text}</span>}
          </div>
        ))}
        {aiLoading && (
          <div className="text-left">
            <div className="inline-block rounded-lg bg-slate-800/80 border border-slate-700 px-3 py-2 max-w-[85%]">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input with Mic Button */}
      <form onSubmit={handleSend} className="border-t border-violet-500/30 px-2 py-2 flex gap-1.5 items-center">
        <button type="button" onClick={toggleListening} className={`h-8 w-8 flex items-center justify-center rounded-lg shrink-0 ${isListening ? "bg-rose-600 text-white animate-pulse" : "bg-slate-800 text-slate-400 hover:text-white"}`} title={isListening ? "Stop listening" : "Speak"} data-testid="livehelp-mic">
          {isListening ? <MicOff size={14} /> : <Mic size={14} />}
        </button>
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder={isListening ? "Listening..." : "Ask anything..."} className="flex-1 h-8 border-slate-700 bg-slate-900 text-slate-100 text-xs" data-testid="livehelp-input" />
        <Button type="submit" disabled={!input.trim() || aiLoading} className="h-8 w-8 p-0 bg-violet-600 hover:bg-violet-500 shrink-0" data-testid="livehelp-send"><Send size={13} /></Button>
      </form>

      <audio ref={remoteAudioRef} autoPlay hidden />
      <video ref={remoteVideoRef} autoPlay playsInline hidden />
    </div>
  );
}
