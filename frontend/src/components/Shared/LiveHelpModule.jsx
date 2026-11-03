import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Send, X, Bug, Minimize2, Maximize2, Monitor, MonitorOff,
  Mic, MicOff, Bot, Volume2, VolumeX, Phone, PhoneOff, Globe,
} from "lucide-react";
import axios from "axios";

const API = "/api";
const WS_BASE = typeof window === "undefined"
  ? ""
  : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;

const LANGUAGES = [
  { code: "en-IN", label: "English" },
  { code: "hi-IN", label: "Hindi" },
  { code: "ta-IN", label: "Tamil" },
  { code: "te-IN", label: "Telugu" },
  { code: "mr-IN", label: "Marathi" },
  { code: "bn-IN", label: "Bengali" },
  { code: "gu-IN", label: "Gujarati" },
  { code: "kn-IN", label: "Kannada" },
  { code: "ml-IN", label: "Malayalam" },
  { code: "pa-IN", label: "Punjabi" },
  { code: "en-US", label: "English (US)" },
];

export function LiveHelpModule({ authHeaders, me }) {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [voiceMode, setVoiceMode] = useState(false);
  const [lang, setLang] = useState("en-IN");
  const [showLangPicker, setShowLangPicker] = useState(false);
  const [sessionId] = useState(() => `help-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`);

  // WebRTC state for admin live support
  const [connected, setConnected] = useState(false);
  const [peerConnected, setPeerConnected] = useState(false);
  const [voiceCallActive, setVoiceCallActive] = useState(false);
  const [screenSharing, setScreenSharing] = useState(false);

  const wsRef = useRef(null);
  const pcRef = useRef(null);
  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const chatEndRef = useRef(null);
  const iceServersRef = useRef([]);
  const recognitionRef = useRef(null);
  const synthRef = useRef(window.speechSynthesis);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Session logging
  const logAction = useCallback(async (action) => {
    try { await axios.post(`${API}/livehelp/log-action`, action, { headers: authHeaders }); } catch (err) { /* non-critical logging */ }
  }, [authHeaders]);

  useEffect(() => {
    if (!authHeaders?.Authorization) return;
    const id = axios.interceptors.response.use(
      (res) => { logAction({ action: "api_call", endpoint: res.config?.url?.replace(API, ""), status: String(res.status) }); return res; },
      (err) => { logAction({ action: "api_error", endpoint: err.config?.url?.replace(API, ""), status: String(err.response?.status || "network"), error: err.response?.data?.detail || err.message }); return Promise.reject(err); }
    );
    return () => axios.interceptors.response.eject(id);
  }, [authHeaders, logAction]);

  // ── Text-to-Speech (AI speaks back) ─────────────────────────────────
  const speak = useCallback((text) => {
    if (!voiceEnabled || !synthRef.current) return;
    synthRef.current.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Pick a voice matching the language
    const voices = synthRef.current.getVoices();
    const match = voices.find(v => v.lang.startsWith(lang.split("-")[0]));
    if (match) utterance.voice = match;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => {
      setIsSpeaking(false);
      // In voice mode, auto-restart listening after AI finishes speaking
      if (voiceMode) {
        setTimeout(() => startListening(), 300);
      }
    };
    utterance.onerror = () => setIsSpeaking(false);
    synthRef.current.speak(utterance);
  }, [voiceEnabled, lang, voiceMode]);

  const stopSpeaking = () => {
    synthRef.current?.cancel();
    setIsSpeaking(false);
  };

  // ── AI Chat ─────────────────────────────────────────────────────────
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
      // Strip raw markdown formatting for clean display
      const cleanReply = (data.reply || "")
        .replace(/\*{2,3}(.*?)\*{2,3}/g, "$1")  // Remove **bold** and ***bold italic***
        .replace(/^#{1,4}\s+/gm, "")              // Remove # headings
        .replace(/^[\-\*]\s+/gm, "- ")            // Normalize bullets
        .replace(/`([^`]+)`/g, "$1")               // Remove inline code
        .replace(/\n{3,}/g, "\n\n")                // Collapse excess newlines
        .trim();
      setMessages(prev => [...prev, {
        type: "ai", text: cleanReply, sender: "AI Support",
        ts: new Date().toISOString(), autoTicket: data.auto_ticket,
      }]);

      // Speak the AI response
      speak(cleanReply);

      if (data.auto_ticket) {
        setMessages(prev => [...prev, { type: "system", text: "Support ticket auto-created for the team.", ts: new Date().toISOString() }]);
      }
    } catch {
      const fallback = "I'm having trouble connecting. Please try the Contact Support option.";
      setMessages(prev => [...prev, { type: "ai", text: fallback, sender: "AI Support", ts: new Date().toISOString() }]);
      speak(fallback);
    }
    setAiLoading(false);
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    stopSpeaking();
    sendToAI(input);
  };

  // ── Speech-to-Text (Voice Input) ───────────────────────────────────
  const startListening = useCallback(() => {
    if (isListening) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setMessages(prev => [...prev, { type: "system", text: "Speech recognition not supported in this browser.", ts: new Date().toISOString() }]);
      return;
    }

    const recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = lang;
    recognitionRef.current = recognition;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map(r => r[0].transcript).join("");
      if (event.results[0].isFinal) {
        setInput("");
        sendToAI(transcript);
      } else {
        setInput(transcript);
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== "no-speech" && event.error !== "aborted") {
        setMessages(prev => [...prev, { type: "system", text: `Mic: ${event.error}`, ts: new Date().toISOString() }]);
      }
      setIsListening(false);
    };

    recognition.start();
  }, [isListening, lang]);

  const stopListening = () => {
    recognitionRef.current?.stop();
    setIsListening(false);
  };

  const toggleMic = () => {
    if (isListening) { stopListening(); }
    else { stopSpeaking(); startListening(); }
  };

  // ── Voice Mode (continuous conversation) ────────────────────────────
  const toggleVoiceMode = () => {
    if (voiceMode) {
      setVoiceMode(false);
      stopListening();
      stopSpeaking();
    } else {
      setVoiceMode(true);
      startListening();
    }
  };

  // ── WebSocket for admin live support ────────────────────────────────
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
          speak(msg.text); // Speak admin messages too
        } else if (msg.type === "peer-joined") {
          setPeerConnected(true);
          setMessages(prev => [...prev, { type: "system", text: `${msg.username || "Admin"} joined live support.`, ts: new Date().toISOString() }]);
        } else if (msg.type === "peer-left") {
          setPeerConnected(false);
        } else if (msg.type === "ice-servers") {
          iceServersRef.current = msg.servers || [];
        } else if (msg.type === "offer") { handleRemoteOffer(msg.sdp); }
        else if (msg.type === "answer") { handleRemoteAnswer(msg.sdp); }
        else if (msg.type === "ice-candidate" && msg.candidate) { handleRemoteIceCandidate(msg.candidate); }
        else if (msg.type === "voice-start") { setVoiceCallActive(true); }
        else if (msg.type === "voice-end") { setVoiceCallActive(false); }
        else if (msg.type === "system-hint") {
          setMessages(prev => [...prev, { type: "hint", text: msg.message, severity: msg.severity, ts: new Date().toISOString() }]);
        }
      } catch (err) { console.error("WS message parse error:", err?.message); }
    };
    ws.onclose = () => { setConnected(false); wsRef.current = null; };
  }, [sessionId, me, speak]);

  const disconnectAll = useCallback(() => {
    stopSpeaking(); stopListening();
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    [localStreamRef, screenStreamRef].forEach(ref => { if (ref.current) { ref.current.getTracks().forEach(t => t.stop()); ref.current = null; } });
    setConnected(false); setPeerConnected(false); setVoiceCallActive(false); setScreenSharing(false); setVoiceMode(false);
  }, []);

  // WebRTC helpers
  const createPC = useCallback(() => {
    const config = iceServersRef.current.length > 0 ? iceServersRef.current : [{ urls: "stun:stun.l.google.com:19302" }];
    const pc = new RTCPeerConnection({ iceServers: config });
    pc.onicecandidate = (e) => { if (e.candidate && wsRef.current) wsRef.current.send(JSON.stringify({ type: "ice-candidate", candidate: e.candidate.toJSON() })); };
    pc.ontrack = (e) => { if (e.track.kind === "audio" && remoteAudioRef.current && e.streams[0]) remoteAudioRef.current.srcObject = e.streams[0]; };
    pcRef.current = pc; return pc;
  }, []);

  const startVoiceCall = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStreamRef.current = stream;
      const pc = createPC();
      stream.getTracks().forEach(t => pc.addTrack(t, stream));
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(JSON.stringify({ type: "offer", sdp: pc.localDescription.toJSON() }));
      wsRef.current?.send(JSON.stringify({ type: "voice-start" }));
      setVoiceCallActive(true);
    } catch (err) { setMessages(prev => [...prev, { type: "system", text: `Mic denied: ${err.message}`, ts: new Date().toISOString() }]); }
  };

  const stopVoiceCall = () => {
    if (localStreamRef.current) { localStreamRef.current.getTracks().forEach(t => t.stop()); localStreamRef.current = null; }
    if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    wsRef.current?.send(JSON.stringify({ type: "voice-end" }));
    setVoiceCallActive(false);
  };

  const startScreenShare = async () => {
    try {
      const ss = await navigator.mediaDevices.getDisplayMedia({ video: { cursor: "always" }, audio: false });
      screenStreamRef.current = ss;
      const pc = pcRef.current || createPC();
      ss.getTracks().forEach(t => { pc.addTrack(t, ss); t.onended = () => stopScreenShare(); });
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(JSON.stringify({ type: "offer", sdp: pc.localDescription.toJSON() }));
      wsRef.current?.send(JSON.stringify({ type: "screen-share-start" }));
      setScreenSharing(true);
    } catch (err) { if (err.name !== "NotAllowedError") setMessages(prev => [...prev, { type: "system", text: `Screen share failed`, ts: new Date().toISOString() }]); }
  };

  const stopScreenShare = () => {
    if (screenStreamRef.current) { screenStreamRef.current.getTracks().forEach(t => t.stop()); screenStreamRef.current = null; }
    wsRef.current?.send(JSON.stringify({ type: "screen-share-end" }));
    setScreenSharing(false);
  };

  const handleRemoteOffer = async (sdp) => { const pc = createPC(); try { const s = await navigator.mediaDevices.getUserMedia({ audio: true }); localStreamRef.current = s; s.getTracks().forEach(t => pc.addTrack(t, s)); } catch (e) { console.error("Mic access failed in offer handler"); } await pc.setRemoteDescription(new RTCSessionDescription(sdp)); const ans = await pc.createAnswer(); await pc.setLocalDescription(ans); wsRef.current?.send(JSON.stringify({ type: "answer", sdp: pc.localDescription.toJSON() })); setVoiceCallActive(true); };
  const handleRemoteAnswer = async (sdp) => { if (pcRef.current) await pcRef.current.setRemoteDescription(new RTCSessionDescription(sdp)); };
  const handleRemoteIceCandidate = async (c) => { if (pcRef.current) { try { await pcRef.current.addIceCandidate(new RTCIceCandidate(c)); } catch (e) { console.error("ICE candidate failed"); } } };

  useEffect(() => { return () => disconnectAll(); }, [disconnectAll]);

  // Welcome message
  useEffect(() => {
    if (open && messages.length === 0) {
      const welcome = "Hi! I'm your AI Support Agent. Ask me anything about the platform. Tap the mic to speak, or type below. I can respond in multiple languages.";
      setMessages([{ type: "ai", text: welcome, sender: "AI Support", ts: new Date().toISOString() }]);
      speak(welcome);
      connectWS();
      // Fetch session hints
      axios.get(`${API}/livehelp/session-analysis`, { headers: authHeaders }).then(res => {
        (res.data.suggestions || []).forEach(s => {
          setMessages(prev => [...prev, { type: "hint", text: s.message, severity: s.severity, ts: new Date().toISOString() }]);
        });
      }).catch((err) => { console.error("Session hints fetch failed:", err?.message); });
    }
  }, [open, messages.length, connectWS, speak, authHeaders]);

  // ── RENDER ──────────────────────────────────────────────────────────
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
    <div className="fixed bottom-20 right-4 sm:right-6 z-50 w-[calc(100vw-2rem)] sm:w-96 max-w-[400px] rounded-xl border border-violet-500/40 bg-slate-950 shadow-2xl shadow-violet-600/10 flex flex-col" style={{ maxHeight: "70vh" }} data-testid="livehelp-panel">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-xl bg-violet-600/20 border-b border-violet-500/30 px-2.5 py-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Bot size={14} className="text-violet-300 shrink-0" />
          <span className="text-xs font-bold text-white truncate">AI Support</span>
          {isSpeaking && <Volume2 size={12} className="text-emerald-400 animate-pulse shrink-0" />}
          {voiceCallActive && <span className="text-[9px] text-emerald-400 animate-pulse">Call</span>}
          {screenSharing && <span className="text-[9px] text-cyan-400 animate-pulse">Screen</span>}
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          {/* Language picker */}
          <button onClick={() => setShowLangPicker(!showLangPicker)} className="p-1 text-slate-400 hover:text-white" title="Language" data-testid="livehelp-lang-btn"><Globe size={12} /></button>
          {/* Voice enable/disable */}
          <button onClick={() => { setVoiceEnabled(!voiceEnabled); if (voiceEnabled) stopSpeaking(); }} className={`p-1 ${voiceEnabled ? "text-emerald-400" : "text-slate-600"}`} title={voiceEnabled ? "Mute AI voice" : "Enable AI voice"} data-testid="livehelp-voice-toggle">
            {voiceEnabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
          </button>
          {/* Admin voice call */}
          {connected && peerConnected && !voiceCallActive && <button onClick={startVoiceCall} className="p-1 text-violet-300 hover:text-white" title="Voice call" data-testid="livehelp-voice-start"><Phone size={12} /></button>}
          {voiceCallActive && <button onClick={stopVoiceCall} className="p-1 text-rose-400" title="End call" data-testid="livehelp-voice-stop"><PhoneOff size={12} /></button>}
          {/* Screen share */}
          {connected && peerConnected && !screenSharing && <button onClick={startScreenShare} className="p-1 text-cyan-300 hover:text-white" title="Share screen" data-testid="livehelp-screen-start"><Monitor size={12} /></button>}
          {screenSharing && <button onClick={stopScreenShare} className="p-1 text-rose-400" data-testid="livehelp-screen-stop"><MonitorOff size={12} /></button>}
          <button onClick={() => { const d = window.prompt("Describe the issue:"); if (d) sendToAI(`Bug report: ${d}`); }} className="p-1 text-amber-400 hover:text-amber-300" title="Report bug" data-testid="livehelp-report-bug"><Bug size={12} /></button>
          <button onClick={() => setMinimized(true)} className="p-1 text-slate-400 hover:text-white"><Minimize2 size={12} /></button>
          <button onClick={() => { setOpen(false); disconnectAll(); }} className="p-1 text-slate-400 hover:text-white" data-testid="livehelp-close"><X size={12} /></button>
        </div>
      </div>

      {/* Language Picker */}
      {showLangPicker && (
        <div className="border-b border-violet-500/20 px-2.5 py-1.5 flex flex-wrap gap-1" data-testid="livehelp-lang-picker">
          {LANGUAGES.map(l => (
            <button key={l.code} onClick={() => { setLang(l.code); setShowLangPicker(false); }} className={`px-2 py-0.5 rounded text-[9px] ${lang === l.code ? "bg-violet-600 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`} data-testid={`lang-${l.code}`}>
              {l.label}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-2.5 py-2 space-y-1.5" style={{ minHeight: 180, maxHeight: "50vh" }}>
        {messages.map((msg, i) => (
          <div key={`msg-${i}`} className={`text-[11px] leading-relaxed ${
            msg.type === "system" ? "text-slate-500 italic text-center" :
            msg.type === "hint" ? `rounded-md px-2 py-1 ${msg.severity === "high" ? "bg-rose-950/40 text-rose-300 border border-rose-700/30" : "bg-amber-950/30 text-amber-300 border border-amber-700/30"}` :
            msg.type === "outgoing" ? "text-right" : "text-left"
          }`}>
            {msg.type === "outgoing" && <div className="inline-block rounded-lg bg-violet-600/30 border border-violet-500/30 px-2.5 py-1.5 max-w-[85%]"><span className="text-violet-200">{msg.text}</span></div>}
            {msg.type === "ai" && (
              <div className="inline-block rounded-lg bg-slate-800/80 border border-slate-700 px-2.5 py-1.5 max-w-[85%]">
                <span className="text-[9px] text-violet-400 flex items-center gap-1 mb-0.5"><Bot size={9} /> AI Support</span>
                <span className="text-slate-200">{msg.text}</span>
                {msg.autoTicket && <span className="text-[9px] text-amber-400 block mt-1">Ticket created</span>}
              </div>
            )}
            {msg.type === "incoming" && <div className="inline-block rounded-lg bg-cyan-900/30 border border-cyan-700/30 px-2.5 py-1.5 max-w-[85%]"><span className="text-[9px] text-cyan-400 block mb-0.5">{msg.sender} (Live Admin)</span><span className="text-slate-200">{msg.text}</span></div>}
            {msg.type === "hint" && <span>{msg.text}</span>}
            {msg.type === "system" && <span>{msg.text}</span>}
          </div>
        ))}
        {aiLoading && (
          <div className="text-left"><div className="inline-block rounded-lg bg-slate-800/80 border border-slate-700 px-3 py-2">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div></div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Voice Mode Banner */}
      {voiceMode && (
        <div className="border-t border-violet-500/20 px-3 py-2 flex items-center justify-between bg-violet-600/10" data-testid="livehelp-voice-mode">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isListening ? "bg-rose-500 animate-pulse" : isSpeaking ? "bg-emerald-500 animate-pulse" : "bg-slate-600"}`} />
            <span className="text-[10px] text-slate-300">
              {isListening ? "Listening..." : isSpeaking ? "Speaking..." : "Ready — tap mic or speak"}
            </span>
          </div>
          <button onClick={toggleVoiceMode} className="text-[10px] text-rose-400 hover:text-rose-300 px-2 py-0.5 border border-rose-500/30 rounded" data-testid="livehelp-exit-voice">Exit Voice</button>
        </div>
      )}

      {/* Input Bar */}
      <form onSubmit={handleSend} className="border-t border-violet-500/30 px-2 py-2 flex gap-1 items-center">
        {!voiceMode ? (
          <>
            <div className="relative flex-1">
              <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder={isListening ? "Listening..." : "Ask anything..."} className="h-8 w-full border-slate-700 bg-slate-900 text-slate-100 text-xs pr-8" data-testid="livehelp-input" />
              <button type="button" onClick={toggleMic} className={`absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded ${isListening ? "text-rose-400 animate-pulse" : "text-slate-500 hover:text-violet-300"}`} title={isListening ? "Stop listening" : "Speak"} data-testid="livehelp-mic">
                {isListening ? <MicOff size={13} /> : <Mic size={13} />}
              </button>
            </div>
            <Button type="submit" disabled={!input.trim() || aiLoading} className="h-8 w-8 p-0 bg-violet-600 hover:bg-violet-500 shrink-0" data-testid="livehelp-send"><Send size={13} /></Button>
            <button type="button" onClick={toggleVoiceMode} className="h-8 w-8 flex items-center justify-center rounded-lg shrink-0 bg-violet-700 text-violet-200 hover:bg-violet-600" title="Switch to Voice Mode" data-testid="livehelp-voice-mode-btn">
              <Phone size={13} />
            </button>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center gap-3 py-1">
            <button type="button" onClick={toggleMic} className={`h-12 w-12 flex items-center justify-center rounded-full ${isListening ? "bg-rose-600 text-white animate-pulse ring-4 ring-rose-600/30" : "bg-violet-700 text-white hover:bg-violet-600"}`} data-testid="livehelp-voice-mic">
              {isListening ? <MicOff size={20} /> : <Mic size={20} />}
            </button>
            {isSpeaking && (
              <button type="button" onClick={stopSpeaking} className="h-8 w-8 flex items-center justify-center rounded-full bg-slate-700 text-slate-300 hover:text-white" title="Stop AI speaking" data-testid="livehelp-stop-speaking">
                <VolumeX size={14} />
              </button>
            )}
          </div>
        )}
      </form>

      <audio ref={remoteAudioRef} autoPlay hidden />
    </div>
  );
}
