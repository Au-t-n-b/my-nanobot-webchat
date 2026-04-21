import { ProviderCommandError } from "../spi/errors.js";

export class ConcurrencyGuard {
  private readonly activeRuns = new Set<string>();
  private readonly activeOutbound = new Set<string>();

  beginRun(toolSessionId: string): void {
    if (this.activeRuns.has(toolSessionId)) {
      throw new ProviderCommandError({
        code: "invalid_input",
        message: "A request run is already active for this toolSessionId",
        details: { reason: "active_run_exists", toolSessionId },
      });
    }
    this.activeRuns.add(toolSessionId);
  }

  endRun(toolSessionId: string): void {
    this.activeRuns.delete(toolSessionId);
  }

  beginOutbound(toolSessionId: string): void {
    if (this.activeOutbound.has(toolSessionId)) {
      throw new ProviderCommandError({
        code: "invalid_input",
        message: "An outbound message stream is already active for this toolSessionId",
        details: { reason: "active_outbound_exists", toolSessionId },
      });
    }
    this.activeOutbound.add(toolSessionId);
  }

  endOutbound(toolSessionId: string): void {
    this.activeOutbound.delete(toolSessionId);
  }
}
