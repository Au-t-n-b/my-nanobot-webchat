import type { InternalStreamChunk } from "../adapters/internal-chat-types.js";
import type { ProviderError, ProviderFact } from "../spi/types.js";
import { providerError } from "../spi/errors.js";
import { normalizeStreamingText } from "./fact-normalize.js";

export interface FactStreamContext {
  toolSessionId: string;
  messageId: string;
  partId: string;
  state: ExecutionState;
}

export interface ExecutionState {
  failed?: ProviderError;
  aborted?: boolean;
}

export class DefaultFactFactory {
  async *stream(
    source: AsyncIterable<InternalStreamChunk>,
    ctx: FactStreamContext,
  ): AsyncIterable<ProviderFact> {
    const { toolSessionId, messageId, partId, state } = ctx;
    yield { type: "message.start", toolSessionId, messageId };

    let acc = "";
    for await (const ch of source) {
      if (ch.kind === "text") {
        const t = normalizeStreamingText(ch.text);
        if (!t) continue;
        acc += t;
        yield { type: "text.delta", toolSessionId, messageId, partId, content: t };
      } else if (ch.kind === "done") {
        break;
      } else if (ch.kind === "aborted") {
        state.aborted = true;
        break;
      } else if (ch.kind === "error") {
        const retryable = Boolean(ch.retryable);
        state.failed = providerError({
          code: retryable ? "provider_unavailable" : "internal_error",
          message: ch.message,
          retryable,
          details: ch.details,
        });
        yield { type: "session.error", toolSessionId, error: state.failed };
        break;
      }
    }

    yield { type: "text.done", toolSessionId, messageId, partId, content: acc };
    yield {
      type: "message.done",
      toolSessionId,
      messageId,
      reason: state.failed ? "error" : state.aborted ? "aborted" : undefined,
    };
  }
}
