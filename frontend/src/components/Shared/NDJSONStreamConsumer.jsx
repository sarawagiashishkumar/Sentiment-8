/**
 * Read an NDJSON stream from a fetch Response.
 * Calls onProgress({type, phase, message}) for progress events.
 * Returns the "complete" event's data payload.
 */
export async function readNDJSONStream(response, onProgress) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  while (true) {
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
  return result;
}
