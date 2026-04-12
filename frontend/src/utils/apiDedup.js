/**
 * API Request Deduplication — prevents concurrent identical requests.
 * If a request to the same URL is already in-flight, returns the existing promise.
 */
const inflightMap = new Map();

export function dedupGet(axios, url, config = {}) {
  const key = `${url}::${JSON.stringify(config.params || {})}`;

  if (inflightMap.has(key)) {
    return inflightMap.get(key);
  }

  const promise = axios
    .get(url, config)
    .finally(() => {
      inflightMap.delete(key);
    });

  inflightMap.set(key, promise);
  return promise;
}

/**
 * Returns IST market hours status for adaptive polling.
 */
export function isMarketHoursIST() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const h = ist.getHours(), m = ist.getMinutes(), day = ist.getDay();
  if (day === 0 || day === 6) return false;
  return (h * 60 + m) >= 555 && (h * 60 + m) <= 930;
}
