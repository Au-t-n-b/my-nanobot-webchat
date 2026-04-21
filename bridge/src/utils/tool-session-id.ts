import { randomUUID } from "node:crypto";

const PREFIX = "sess_";

/** Cryptographically random external session id (never derive from host thread_id). */
export function createSecureToolSessionId(): string {
  return `${PREFIX}${randomUUID()}`;
}
