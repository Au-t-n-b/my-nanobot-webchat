import type { InternalChatPort } from "../adapters/internal-chat-port.js";
import { parseWelinkCreateSessionTitle } from "../adapters/welink-session-meta.js";
import type { InternalChatCredentials } from "../adapters/internal-chat-types.js";
import { WelinkNanobotProxyAdapter } from "../adapters/welink-nanobot-proxy-adapter.js";
import type { SessionRegistry } from "../session/session-registry.js";
import type {
  ProviderAbortSessionInput,
  ProviderCloseSessionInput,
  ProviderCreateSessionInput,
  ProviderCreateSessionResult,
  ProviderHealthInput,
  ProviderHealthResult,
  ProviderPermissionReplyInput,
  ProviderQuestionReplyInput,
  ProviderRun,
  ProviderRunMessageInput,
  ProviderRuntimeContext,
  ThirdPartyAgentProvider,
} from "../spi/types.js";
import { ProviderCommandError } from "../spi/errors.js";
import { createSecureToolSessionId } from "../utils/tool-session-id.js";
import { ConcurrencyGuard } from "../runtime/concurrency-guard.js";
import { OutboundController } from "../runtime/outbound-controller.js";
import { buildProviderRun } from "../runtime/run-controller.js";
import type { InternalChatConfigShape } from "../config/bridge-config.js";
import { mergeInternalChat } from "../config/loader.js";
import type { BridgeRootConfigShape } from "../config/bridge-config.js";
import { requireInternalChatCredentials, resolveInternalChatCredentials } from "../config/env.js";
import { InMemorySessionRegistry } from "../session/in-memory-session-registry.js";
import type { SessionRecord } from "../session/session-types.js";

export interface BridgeProviderOptions {
  /** Merged internal_chat + defaults */
  internalChat: InternalChatConfigShape;
  chat?: InternalChatPort;
  sessions?: SessionRegistry;
  concurrency?: ConcurrencyGuard;
  outbound?: OutboundController;
}

export class BridgeProvider implements ThirdPartyAgentProvider {
  private readonly internalChat: InternalChatConfigShape;
  private readonly chat: InternalChatPort;
  private readonly sessions: SessionRegistry;
  private readonly concurrency: ConcurrencyGuard;
  private readonly outbound: OutboundController;
  private readonly activeRunAbort = new Map<string, AbortController>();

  constructor(opts: BridgeProviderOptions) {
    this.internalChat = opts.internalChat;
    this.chat =
      opts.chat ??
      new WelinkNanobotProxyAdapter({
        apiBaseUrl: opts.internalChat.api_base_url,
        streamPath: opts.internalChat.stream_path,
        timeoutMs: opts.internalChat.timeout_ms,
        welinkAuthTokenEnv: opts.internalChat.welink_auth_token_env,
      });
    this.sessions = opts.sessions ?? new InMemorySessionRegistry();
    this.concurrency = opts.concurrency ?? new ConcurrencyGuard();
    this.outbound = opts.outbound ?? new OutboundController(this.concurrency);
  }

  async initialize(context: ProviderRuntimeContext): Promise<void> {
    this.outbound.setContext(context);
  }

  async health(input: ProviderHealthInput): Promise<ProviderHealthResult> {
    void input.traceId;
    const creds = resolveInternalChatCredentials(this.internalChat);
    if (!creds.assistantId) {
      return { online: false };
    }
    try {
      await this.chat.ping(input.traceId, creds);
      return { online: true };
    } catch {
      return { online: false };
    }
  }

  async createSession(input: ProviderCreateSessionInput): Promise<ProviderCreateSessionResult> {
    const welink = parseWelinkCreateSessionTitle(input.title);
    const credentials = requireInternalChatCredentials(this.internalChat);
    const toolSessionId = createSecureToolSessionId();
    const { threadId } = await this.chat.createThread({
      traceId: input.traceId,
      title: input.title,
      credentials,
      welink,
    });
    const record: SessionRecord = {
      toolSessionId,
      threadId,
      toolSessionIdSource: "provider",
      createdAtMs: Date.now(),
      title: input.title,
      assistantId: input.assistantId ?? credentials.assistantId,
      welink,
    };
    this.sessions.bind(record);
    return { toolSessionId, title: input.title };
  }

  async runMessage(input: ProviderRunMessageInput): Promise<ProviderRun> {
    const credentials = requireInternalChatCredentials(this.internalChat);
    const rec = this.sessions.getByToolSessionId(input.toolSessionId);
    if (!rec?.welink) {
      throw new ProviderCommandError({
        code: "not_found",
        message: "Unknown toolSessionId or session missing WeLink metadata",
        details: { toolSessionId: input.toolSessionId },
      });
    }
    this.concurrency.beginRun(input.toolSessionId);
    const ac = new AbortController();
    this.activeRunAbort.set(input.toolSessionId, ac);
    const onRunFinished = () => {
      this.concurrency.endRun(input.toolSessionId);
      this.activeRunAbort.delete(input.toolSessionId);
    };
    try {
      return buildProviderRun({
        traceId: input.traceId,
        runId: input.runId,
        toolSessionId: input.toolSessionId,
        threadId: rec.threadId,
        userText: input.text,
        credentials,
        welink: rec.welink,
        chat: this.chat,
        signal: ac.signal,
        onRunFinished,
      });
    } catch (e) {
      onRunFinished();
      throw e;
    }
  }

  async replyQuestion(input: ProviderQuestionReplyInput): Promise<{ applied: true }> {
    const rec = this.sessions.getByToolSessionId(input.toolSessionId);
    if (!rec) {
      throw new ProviderCommandError({
        code: "not_found",
        message: "Unknown toolSessionId",
        details: { toolSessionId: input.toolSessionId },
      });
    }
    const credentials = requireInternalChatCredentials(this.internalChat);
    await this.chat.replyQuestion({
      traceId: input.traceId,
      threadId: rec.threadId,
      toolCallId: input.toolCallId,
      answer: input.answer,
      credentials,
    });
    return { applied: true };
  }

  async replyPermission(input: ProviderPermissionReplyInput): Promise<{ applied: true }> {
    const rec = this.sessions.getByToolSessionId(input.toolSessionId);
    if (!rec) {
      throw new ProviderCommandError({
        code: "not_found",
        message: "Unknown toolSessionId",
        details: { toolSessionId: input.toolSessionId },
      });
    }
    const credentials = requireInternalChatCredentials(this.internalChat);
    await this.chat.replyPermission({
      traceId: input.traceId,
      threadId: rec.threadId,
      permissionId: input.permissionId,
      response: input.response,
      credentials,
    });
    return { applied: true };
  }

  async closeSession(input: ProviderCloseSessionInput): Promise<{ applied: true }> {
    const rec = this.sessions.getByToolSessionId(input.toolSessionId);
    if (!rec) {
      throw new ProviderCommandError({
        code: "not_found",
        message: "Unknown toolSessionId",
        details: { toolSessionId: input.toolSessionId },
      });
    }
    const credentials = requireInternalChatCredentials(this.internalChat);
    await this.chat.closeThread({
      traceId: input.traceId,
      threadId: rec.threadId,
      credentials,
    });
    this.sessions.remove(input.toolSessionId);
    return { applied: true };
  }

  async abortSession(input: ProviderAbortSessionInput): Promise<{ applied: true }> {
    const rec = this.sessions.getByToolSessionId(input.toolSessionId);
    if (!rec) {
      throw new ProviderCommandError({
        code: "not_found",
        message: "Unknown toolSessionId",
        details: { toolSessionId: input.toolSessionId },
      });
    }
    const credentials = requireInternalChatCredentials(this.internalChat);
    const ac = this.activeRunAbort.get(input.toolSessionId);
    ac?.abort();
    await this.chat.abortThread({
      traceId: input.traceId,
      threadId: rec.threadId,
      runId: input.runId,
      credentials,
    });
    return { applied: true };
  }

  async dispose(): Promise<void> {
    this.activeRunAbort.clear();
  }
}

export function createBridgeProviderFromConfigJson(
  cfg: BridgeRootConfigShape = {},
  overrides?: Partial<BridgeProviderOptions>,
): BridgeProvider {
  const internalChat = mergeInternalChat(cfg);
  if (!internalChat.api_base_url?.trim()) {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "internal_chat.api_base_url is required in config.json for WelinkNanobotProxyAdapter",
    });
  }
  return new BridgeProvider({ internalChat, ...overrides });
}
