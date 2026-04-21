import test from "node:test";
import assert from "node:assert/strict";
import { BridgeProvider } from "../provider/bridge-provider.js";
import type { InternalChatPort } from "../adapters/internal-chat-port.js";
import type { InternalStreamChunk } from "../adapters/internal-chat-types.js";
import { ProviderCommandError } from "../spi/errors.js";

const internalChat = {
  api_base_url: "http://127.0.0.1:9",
  assistant_id_env: "INTERNAL_CHAT_ASSISTANT_ID",
  assistant_secret_env: "INTERNAL_CHAT_ASSISTANT_SECRET",
  welink_auth_token_env: "WELINK_AUTH_TOKEN",
  timeout_ms: 2000,
  stream_path: "/welink/chat/stream",
};

class FakeChat implements InternalChatPort {
  async ping(): Promise<void> {
    return;
  }
  async createThread(): Promise<{ threadId: string }> {
    return { threadId: "welink:u:t" };
  }
  async closeThread(): Promise<void> {}
  async abortThread(): Promise<void> {}
  async *streamAssistantReply(): AsyncIterable<InternalStreamChunk> {
    yield { kind: "text", text: "ok" };
    yield { kind: "done" };
  }
  async replyQuestion(): Promise<void> {
    throw new ProviderCommandError({ code: "not_supported", message: "test" });
  }
  async replyPermission(): Promise<void> {
    throw new ProviderCommandError({ code: "not_supported", message: "test" });
  }
}

test("health offline when assistant id missing", async () => {
  const prev = process.env.INTERNAL_CHAT_ASSISTANT_ID;
  delete process.env.INTERNAL_CHAT_ASSISTANT_ID;
  const p = new BridgeProvider({ internalChat, chat: new FakeChat() });
  const h = await p.health({ traceId: "t1" });
  assert.equal(h.online, false);
  if (prev !== undefined) process.env.INTERNAL_CHAT_ASSISTANT_ID = prev;
});

test("createSession and runMessage happy path", async () => {
  process.env.INTERNAL_CHAT_ASSISTANT_ID = "aid";
  process.env.INTERNAL_CHAT_ASSISTANT_SECRET = "sec";
  const p = new BridgeProvider({ internalChat, chat: new FakeChat() });
  const title = JSON.stringify({ welink: { sendUserAccount: "u", topicId: "tid" } });
  const { toolSessionId } = await p.createSession({ traceId: "t1", title });
  assert.match(toolSessionId, /^sess_/);
  const run = await p.runMessage({ traceId: "t1", runId: "r1", toolSessionId, text: "hello" });
  const types: string[] = [];
  for await (const f of run.facts) {
    types.push(f.type);
  }
  const r = await run.result();
  assert.equal(r.outcome, "completed");
  assert.ok(types.includes("message.start"));
  delete process.env.INTERNAL_CHAT_ASSISTANT_ID;
  delete process.env.INTERNAL_CHAT_ASSISTANT_SECRET;
});

test("runMessage not_found for unknown session", async () => {
  process.env.INTERNAL_CHAT_ASSISTANT_ID = "aid";
  process.env.INTERNAL_CHAT_ASSISTANT_SECRET = "sec";
  const p = new BridgeProvider({ internalChat, chat: new FakeChat() });
  await assert.rejects(
    () => p.runMessage({ traceId: "t1", runId: "r1", toolSessionId: "sess_missing", text: "x" }),
    (e: unknown) => e instanceof ProviderCommandError && e.code === "not_found",
  );
  delete process.env.INTERNAL_CHAT_ASSISTANT_ID;
  delete process.env.INTERNAL_CHAT_ASSISTANT_SECRET;
});
