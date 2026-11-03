import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { AlertTriangle, X } from "lucide-react";
import { Button } from "components/ui/button";

const API = "/api";

export function FNOEventPopup({ authHeaders }) {
  const [events, setEvents] = useState([]);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/fno/events`, { headers: authHeaders });
      setEvents(res.data || []);
    } catch {
      // silent
    }
  }, [authHeaders]);

  useEffect(() => {
    fetchEvents();
    const timer = setInterval(fetchEvents, 30000);
    return () => clearInterval(timer);
  }, [fetchEvents]);

  const acknowledgeEvent = async (eventId) => {
    try {
      await axios.post(`${API}/fno/events/acknowledge`, { event_id: eventId }, { headers: authHeaders });
      setEvents((prev) => prev.filter((e) => e.event_id !== eventId));
    } catch {
      // silent
    }
  };

  if (!events.length) return null;

  return (
    <div className="space-y-2" data-testid="fno-event-popup-container">
      {events.map((evt) => {
        const isUrgent = evt.event_type === "URGENT_EXIT";
        const bgClass = isUrgent
          ? "border-red-500 bg-red-500/20 text-red-100"
          : evt.event_type === "REGIME_SHIFT"
          ? "border-amber-500 bg-amber-500/20 text-amber-100"
          : "border-cyan-500 bg-cyan-500/20 text-cyan-100";
        return (
          <div key={evt.event_id} className={`flex items-start justify-between gap-2 rounded-md border px-3 py-2 text-xs ${bgClass}`} data-testid={`fno-event-${evt.event_id}`}>
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold">{evt.event_type}: {evt.payload?.symbol || evt.signal_id}</p>
                {evt.payload?.message && <p className="mt-0.5 text-[11px] opacity-80">{evt.payload.message}</p>}
              </div>
            </div>
            <Button type="button" onClick={() => acknowledgeEvent(evt.event_id)} className="h-6 w-6 shrink-0 bg-transparent p-0 hover:bg-white/10" data-testid={`fno-event-ack-${evt.event_id}`}>
              <X size={12} />
            </Button>
          </div>
        );
      })}
    </div>
  );
}
