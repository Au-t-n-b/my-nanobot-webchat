import type { EmitOutboundMessageInput, OutboundFact, ProviderRuntimeContext } from "../spi/types.js";
import { ProviderCommandError } from "../spi/errors.js";
import { ConcurrencyGuard } from "./concurrency-guard.js";

export class OutboundController {
  private emitter: ProviderRuntimeContext["outbound"] | undefined;

  constructor(private readonly guard: ConcurrencyGuard) {}

  setContext(ctx: ProviderRuntimeContext): void {
    this.emitter = ctx.outbound;
  }

  async emit(input: Omit<EmitOutboundMessageInput, "facts"> & { facts: AsyncIterable<OutboundFact> }): Promise<{
    applied: true;
  }> {
    if (!this.emitter) {
      throw new ProviderCommandError({
        code: "internal_error",
        message: "Runtime outbound emitter not initialized; call initialize() first",
      });
    }
    this.guard.beginOutbound(input.toolSessionId);
    try {
      await this.emitter.emitOutboundMessage({
        toolSessionId: input.toolSessionId,
        messageId: input.messageId,
        trigger: input.trigger,
        facts: input.facts,
        assistantId: input.assistantId,
      });
      return { applied: true };
    } finally {
      this.guard.endOutbound(input.toolSessionId);
    }
  }
}
