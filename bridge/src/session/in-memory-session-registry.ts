import type { SessionRegistry } from "./session-registry.js";
import type { SessionRecord } from "./session-types.js";

export class InMemorySessionRegistry implements SessionRegistry {
  private readonly byTool = new Map<string, SessionRecord>();

  bind(record: SessionRecord): void {
    this.byTool.set(record.toolSessionId, { ...record });
  }

  bindPlatformSession(record: SessionRecord): void {
    this.bind(record);
  }

  getByToolSessionId(toolSessionId: string): SessionRecord | undefined {
    const r = this.byTool.get(toolSessionId);
    return r ? { ...r } : undefined;
  }

  remove(toolSessionId: string): void {
    this.byTool.delete(toolSessionId);
  }
}
