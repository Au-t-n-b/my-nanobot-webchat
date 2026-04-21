const SENSITIVE_KEYS = new Set([
  "authorization",
  "assistantsecret",
  "assistant_secret",
  "secret",
  "token",
  "password",
]);

/** Shallow redact for logging / error.details. */
export function redactHeaders(h: Record<string, string> | undefined): Record<string, string> | undefined {
  if (!h) return undefined;
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(h)) {
    if (SENSITIVE_KEYS.has(k.toLowerCase())) {
      out[k] = "[REDACTED]";
    } else {
      out[k] = v;
    }
  }
  return out;
}
