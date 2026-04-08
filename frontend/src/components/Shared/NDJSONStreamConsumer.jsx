/**
 * Read an NDJSON stream from a fetch Response.
 * Calls onProgress({type, phase, message}) for progress events.
 * Returns the "complete" event's data payload.
 *
 * Accepts an optional AbortSignal to clean up the reader on unmount.
 */
export async function readNDJSONStream(response, onProgress, signal) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  // If an AbortSignal is provided, cancel the reader when aborted
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
          } else if (event.type === "complete") {
            result = event.data;
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
      } catch {
        // skip
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      // Stream was intentionally cancelled — not an error
      return result;
    }
    throw err;
  }
  return result;
}
