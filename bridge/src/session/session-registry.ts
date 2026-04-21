import type { SessionRecord } from "./session-types.js";

export interface SessionRegistry {
  bind(record: SessionRecord): void;
  getByToolSessionId(toolSessionId: string): SessionRecord | undefined;
  remove(toolSessionId: string): void;
  /** Reserved for Runtime-preallocated toolSessionId + host thread binding (low-cost migration). */
  bindPlatformSession?(record: SessionRecord): void;
}
