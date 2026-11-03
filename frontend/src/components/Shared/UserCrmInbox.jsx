import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { X, MessageSquare, Send, Reply } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const API = "/api";

export function UserCrmInbox({ authHeaders }) {
  const [messages, setMessages] = useState([]);
  const [unread, setUnread] = useState(0);
  const [expanded, setExpanded] = useState(null);
  const [showContact, setShowContact] = useState(false);
  const [contactForm, setContactForm] = useState({ subject: "", body: "" });
  const [replyText, setReplyText] = useState("");

  const fetch = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/inbox`, { headers: authHeaders });
      setMessages(res.data.messages || []);
      setUnread(res.data.unread || 0);
    } catch (err) { console.error("Failed to fetch CRM inbox:", err?.message); }
  }, [authHeaders]);

  useEffect(() => { fetch(); const t = setInterval(fetch, 60000); return () => clearInterval(t); }, [fetch]);

  const dismiss = async (msgId) => {
    await axios.patch(`${API}/crm/dismiss/${msgId}`, {}, { headers: authHeaders });
    fetch();
  };

  const markRead = async (msgId) => {
    await axios.patch(`${API}/crm/read/${msgId}`, {}, { headers: authHeaders });
    fetch();
  };

  const reply = async (msgId) => {
    if (!replyText.trim()) return;
    await axios.post(`${API}/crm/reply/${msgId}`, { body: replyText }, { headers: authHeaders });
    setReplyText("");
    setExpanded(null);
    fetch();
  };

  const sendContact = async (e) => {
    e.preventDefault();
    if (!contactForm.body.trim()) return;
    await axios.post(`${API}/crm/contact`, contactForm, { headers: authHeaders });
    setContactForm({ subject: "", body: "" });
    setShowContact(false);
  };

  if (messages.length === 0 && !showContact) return null;

  return (
    <div className="mb-4 space-y-2" data-testid="user-crm-inbox">
      {messages.length > 0 && (
        <div className="space-y-1.5">
          {messages.map(msg => (
            <div key={msg.message_id} className={`rounded-lg border px-3 py-2 ${msg.status === "unread" ? "border-violet-500/40 bg-violet-950/20" : "border-slate-700/50 bg-slate-900/30"}`} data-testid={`user-msg-${msg.message_id}`}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <MessageSquare size={11} className="text-violet-400 shrink-0" />
                    <span className="text-xs font-bold text-white truncate">{msg.subject}</span>
                    {msg.priority === "critical" && <span className="text-[9px] bg-rose-500/20 text-rose-300 px-1 rounded">Urgent</span>}
                  </div>
                  <p className="text-[10px] text-slate-300 mt-0.5 line-clamp-2">{msg.body}</p>
                  <span className="text-[9px] text-slate-600">{msg.from_username} - {msg.ts ? new Date(msg.ts).toLocaleString("en-IN") : ""}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {msg.status === "unread" && (
                    <button onClick={() => markRead(msg.message_id)} className="text-[9px] text-violet-400 hover:text-violet-300 px-1">Read</button>
                  )}
                  <button onClick={() => setExpanded(expanded === msg.message_id ? null : msg.message_id)} className="p-0.5 text-cyan-400 hover:text-cyan-300"><Reply size={11} /></button>
                  <button onClick={() => dismiss(msg.message_id)} className="p-0.5 text-slate-600 hover:text-rose-400"><X size={11} /></button>
                </div>
              </div>
              {expanded === msg.message_id && (
                <div className="mt-2 flex gap-1.5">
                  <Input value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="Reply..." className="flex-1 h-7 border-slate-700 bg-slate-800 text-slate-100 text-[10px]" data-testid={`reply-input-${msg.message_id}`} />
                  <Button onClick={() => reply(msg.message_id)} className="h-7 w-7 p-0 bg-violet-600"><Send size={10} /></Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showContact && (
        <form onSubmit={sendContact} className="rounded-lg border border-cyan-500/30 bg-cyan-950/10 p-3 space-y-2" data-testid="user-contact-form">
          <Input value={contactForm.subject} onChange={(e) => setContactForm(p => ({ ...p, subject: e.target.value }))} placeholder="Subject" className="h-7 border-slate-700 bg-slate-800 text-slate-100 text-xs" />
          <textarea value={contactForm.body} onChange={(e) => setContactForm(p => ({ ...p, body: e.target.value }))} placeholder="How can we help?" rows={2} className="w-full rounded border border-slate-700 bg-slate-800 text-slate-100 text-xs p-2 resize-none" />
          <div className="flex gap-2">
            <Button type="submit" className="h-7 bg-cyan-600 text-white text-[10px]"><Send size={10} className="mr-1" /> Send</Button>
            <Button type="button" onClick={() => setShowContact(false)} variant="ghost" className="h-7 text-[10px] text-slate-400">Cancel</Button>
          </div>
        </form>
      )}

      {!showContact && (
        <button onClick={() => setShowContact(true)} className="text-[10px] text-cyan-400 hover:text-cyan-300" data-testid="user-contact-trigger">
          <Send size={10} className="inline mr-1" /> Contact Support
        </button>
      )}
    </div>
  );
}
