import type { InternalChatPort } from "../adapters/internal-chat-port.js";
import type { InternalChatCredentials } from "../adapters/internal-chat-types.js";
import type { WelinkCreateSessionMeta } from "../adapters/welink-session-meta.js";
import type { ProviderFact, ProviderRun, ProviderTerminalResult } from "../spi/types.js";
import { DefaultFactFactory, type ExecutionState } from "../facts/fact-factory.js";
import { createMessageId, createPartId } from "../utils/ids.js";

export function buildProviderRun(input: {
  traceId: string;
  runId: string;
  toolSessionId: string;
  threadId: string;
  userText: string;
  credentials: InternalChatCredentials;
  welink: WelinkCreateSessionMeta;
  chat: InternalChatPort;
  onRunFinished: () => void;
  signal?: AbortSignal;
}): ProviderRun {
  const messageId = createMessageId();
  const partId = createPartId();
  const state: ExecutionState = {};
  let settled = false;
  let resolveResult!: (v: ProviderTerminalResult) => void;
  const resultPromise = new Promise<ProviderTerminalResult>((resolve) => {
    resolveResult = resolve;
  });

  const settle = (r: ProviderTerminalResult) => {
    if (settled) return;
    settled = true;
    resolveResult(r);
  };

  async function* innerFacts(): AsyncIterable<ProviderFact> {
    const factory = new DefaultFactFactory();
    const stream = input.chat.streamAssistantReply({
      traceId: input.traceId,
      runId: input.runId,
      threadId: input.threadId,
      userText: input.userText,
      credentials: input.credentials,
      welink: input.welink,
      messageId: messageId,
      signal: input.signal,
    });
    for await (const f of factory.stream(stream, {
      toolSessionId: input.toolSessionId,
      messageId,
      partId,
      state,
    })) {
      yield f;
    }
    if (state.aborted) {
      settle({ outcome: "aborted" });
    } else if (state.failed) {
      settle({ outcome: "failed", error: state.failed });
    } else {
      settle({ outcome: "completed" });
    }
  }

  async function* factsGen(): AsyncIterable<ProviderFact> {
    try {
      for await (const f of innerFacts()) {
        yield f;
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      settle({
        outcome: "failed",
        error: {
          code: "internal_error",
          message,
          details: { runId: input.runId },
        },
      });
      throw e;
    } finally {
      input.onRunFinished();
    }
  }

  return {
    runId: input.runId,
    facts: factsGen(),
    result: () => resultPromise,
  };
}
