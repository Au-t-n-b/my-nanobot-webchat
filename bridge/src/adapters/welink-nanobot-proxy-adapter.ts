import type { InternalChatPort, CreateThreadInput } from "./internal-chat-port.js";
import type { InternalChatCredentials, InternalStreamChunk, InternalThreadId } from "./internal-chat-types.js";
import { ProviderCommandError } from "../spi/errors.js";
import { welinkThreadId } from "./welink-session-meta.js";
import type { WelinkCreateSessionMeta } from "./welink-session-meta.js";
import { redactHeaders } from "../utils/redact.js";

export interface WelinkNanobotProxyAdapterOptions {
  apiBaseUrl: string;
  streamPath: string;
  timeoutMs: number;
  /** Read token from process.env[name] for Authorization header (matches nanobot /welink/chat/stream). */
  welinkAuthTokenEnv: string;
}

function normalizeBase(url: string): string {
  return url.replace(/\/+$/, "");
}

async function* parseSseDataLines(body: ReadableStream<Uint8Array> | null): AsyncIterable<string> {
  if (!body) {
    throw new ProviderCommandError({
      code: "provider_unavailable",
      message: "Response has no body stream",
    });
  }
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      for (;;) {
        const sep = buffer.indexOf("\n\n");
        if (sep < 0) break;
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        yield block;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseWelinkSseBlock(block: string): InternalStreamChunk | null {
  const lines = block.split("\n");
  for (const line of lines) {
    if (!line.startsWith("data:")) continue;
    const raw = line.slice(5).trim();
    if (!raw) continue;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return { kind: "error", message: "Invalid SSE JSON", retryable: false };
    }
    const code = String(payload.code ?? "");
    const isFinish = Boolean(payload.isFinish);
    const message = typeof payload.message === "string" ? payload.message : undefined;

    if (code !== "0") {
      return {
        kind: "error",
        message: message || `WeLink stream error code=${code}`,
        retryable: code === "429" || code === "503",
        details: { code, raw: payload },
      };
    }

    if (isFinish) {
      return { kind: "done", usage: undefined };
    }

    const data = payload.data as Record<string, unknown> | undefined;
    const text = data && typeof data.text === "string" ? String(data.text) : "";

    if (text.length > 0) {
      return { kind: "text", text };
    }
    return null;
  }
  return null;
}

export class WelinkNanobotProxyAdapter implements InternalChatPort {
  constructor(private readonly opts: WelinkNanobotProxyAdapterOptions) {}

  private authHeader(): Record<string, string> {
    const name = this.opts.welinkAuthTokenEnv || "WELINK_AUTH_TOKEN";
    const token = (process.env[name] || "").trim();
    if (!token) return {};
    return { Authorization: token };
  }

  async ping(_traceId: string, _credentials: InternalChatCredentials): Promise<void> {
    const base = normalizeBase(this.opts.apiBaseUrl);
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.opts.timeoutMs);
    try {
      const res = await fetch(base, { method: "GET", signal: ctrl.signal, redirect: "follow" });
      if (!res.ok && res.status >= 500) {
        throw new ProviderCommandError({
          code: "provider_unavailable",
          message: `Health check GET ${base} failed: ${res.status}`,
          details: { status: res.status },
        });
      }
    } catch (e) {
      if (e instanceof ProviderCommandError) throw e;
      const msg = e instanceof Error ? e.message : String(e);
      throw new ProviderCommandError({
        code: "provider_unavailable",
        message: `Health check failed: ${msg}`,
        details: { baseUrl: base },
      });
    } finally {
      clearTimeout(t);
    }
  }

  async createThread(input: CreateThreadInput): Promise<{ threadId: InternalThreadId }> {
    return { threadId: welinkThreadId(input.welink) };
  }

  async closeThread(_input: {
    traceId: string;
    threadId: InternalThreadId;
    credentials: InternalChatCredentials;
  }): Promise<void> {
    /* No nanobot HTTP close for WeLink topic in MVP. */
  }

  async abortThread(_input: {
    traceId: string;
    threadId: InternalThreadId;
    runId?: string;
    credentials: InternalChatCredentials;
  }): Promise<void> {
    /* Abort is driven by AbortSignal on the active stream. */
  }

  async *streamAssistantReply(input: {
    traceId: string;
    runId: string;
    threadId: InternalThreadId;
    userText: string;
    credentials: InternalChatCredentials;
    welink: WelinkCreateSessionMeta;
    messageId: string;
    signal?: AbortSignal;
  }): AsyncIterable<InternalStreamChunk> {
    const base = `${normalizeBase(this.opts.apiBaseUrl)}/`;
    const path = this.opts.streamPath.startsWith("/")
      ? this.opts.streamPath
      : `/${this.opts.streamPath}`;
    const url = new URL(path, base).href;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...this.authHeader(),
    };
    const body = JSON.stringify({
      type: "text",
      content: input.userText,
      sendUserAccount: input.welink.sendUserAccount,
      topicId: input.welink.topicId,
      messageId: input.messageId,
    });
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.opts.timeoutMs);
    const signal = input.signal;
    if (signal) {
      if (signal.aborted) ctrl.abort();
      else signal.addEventListener("abort", () => ctrl.abort(), { once: true });
    }
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers,
        body,
        signal: ctrl.signal,
      });
    } catch (e) {
      clearTimeout(t);
      const name = e instanceof Error ? e.name : "";
      if (name === "AbortError" || (e instanceof Error && e.message.includes("abort"))) {
        yield { kind: "aborted" };
        return;
      }
      const msg = e instanceof Error ? e.message : String(e);
      yield { kind: "error", message: msg, retryable: true, details: { url, headers: redactHeaders(headers) } };
      return;
    } finally {
      clearTimeout(t);
    }

    if (res.status === 401 || res.status === 403) {
      yield {
        kind: "error",
        message: `WeLink auth failed: HTTP ${res.status}`,
        retryable: false,
        details: { status: res.status },
      };
      return;
    }
    if (res.status === 404) {
      yield {
        kind: "error",
        message: `WeLink stream endpoint not found: HTTP 404`,
        retryable: false,
        details: { url },
      };
      return;
    }
    if (res.status === 429) {
      yield {
        kind: "error",
        message: "WeLink rate limited (HTTP 429)",
        retryable: true,
        details: { status: 429 },
      };
      return;
    }
    if (res.status >= 500) {
      yield {
        kind: "error",
        message: `WeLink server error: HTTP ${res.status}`,
        retryable: true,
        details: { status: res.status },
      };
      return;
    }
    if (!res.ok) {
      yield {
        kind: "error",
        message: `WeLink unexpected HTTP ${res.status}`,
        retryable: res.status >= 500,
        details: { status: res.status },
      };
      return;
    }

    try {
      for await (const block of parseSseDataLines(res.body)) {
        const chunk = parseWelinkSseBlock(block);
        if (chunk) yield chunk;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      yield { kind: "error", message: msg, retryable: true };
    }
  }

  async replyQuestion(_input: {
    traceId: string;
    threadId: InternalThreadId;
    toolCallId: string;
    answer: string;
    credentials: InternalChatCredentials;
  }): Promise<void> {
    throw new ProviderCommandError({
      code: "not_supported",
      message: "replyQuestion is not supported for WelinkNanobotProxyAdapter in this version",
    });
  }

  async replyPermission(_input: {
    traceId: string;
    threadId: InternalThreadId;
    permissionId: string;
    response: "once" | "always" | "reject";
    credentials: InternalChatCredentials;
  }): Promise<void> {
    throw new ProviderCommandError({
      code: "not_supported",
      message: "replyPermission is not supported for WelinkNanobotProxyAdapter in this version",
    });
  }
}
