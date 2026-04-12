/**
 * Environment-aware logger that silences debug/warn in production.
 * console.error always logs for critical issues.
 */
const isDev = process.env.NODE_ENV !== "production";

export const logger = {
  debug: isDev ? console.debug.bind(console) : () => {},
  warn: isDev ? console.warn.bind(console) : () => {},
  error: console.error.bind(console),
};
