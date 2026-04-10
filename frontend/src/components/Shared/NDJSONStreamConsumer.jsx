/**
 * Read an NDJSON stream from a fetch Response.
 * Calls onProgress({type, phase, message}) for progress events.
 * Calls onPartial({phase, data}) for partial result events (NIFTY/BANKNIFTY done early).
 * Returns the "complete" event's data payload.
 *
 * Accepts an optional AbortSignal to clean up the reader on unmount.
 */
export async function readNDJSONStream(response, onProgress, signal, onPartial) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  if (signal) {
    signal.addEventListener("abort", () => {
      try { reader.cancel(); } catch { /* already closed */ }
    }, { once: true });
  }

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          if (event.type === "progress" && onProgress) {
            onProgress(event);
          } else if (event.type === "partial" && onPartial) {
            onPartial(event);
          } else if (event.type === "complete") {
            result = event.data;
          } else if (event.type === "keepalive") {
            // Keep-alive heartbeat — ignore silently, prevents proxy timeout
          }
        } catch {
          // skip malformed lines
        }
      }
    }
    // Process any remaining buffer
    if (buffer.trim()) {
      try {
        const event = JSON.parse(buffer);
        if (event.type === "complete") result = event.data;
        else if (event.type === "partial" && onPartial) onPartial(event);
      } catch {
        // skip
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      return result;
    }
    throw err;
  }
  return result;
}
