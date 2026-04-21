#!/usr/bin/env node
/**
 * Local smoke for Path B: BridgeProvider (v2 SPI) -> AGUI /welink/chat/stream.
 *
 * Prerequisites:
 *   1. AGUI running (e.g. npm run dev or python -m nanobot agui).
 *   2. ~/.nanobot/config.json with internalChat.apiBaseUrl (or internal_chat.api_base_url) = AGUI root, e.g. http://127.0.0.1:8765
 *   3. Env: INTERNAL_CHAT_ASSISTANT_ID, INTERNAL_CHAT_ASSISTANT_SECRET (any non-empty strings for local test)
 *   4. If AGUI requires WeLink route auth: WELINK_AUTH_TOKEN matching server env
 *
 * Optional env:
 *   SMOKE_SEND_USER (default testuser)  SMOKE_TOPIC_ID (default topic-local-1)  SMOKE_TEXT (default 你好)
 *
 * Usage (from repo nanobot/bridge/ after npm run build):
 *   node scripts/smoke-local.mjs
 */
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const { createBridgeProvider } = await import(join(root, "dist", "index.js"));

const sendUser = process.env.SMOKE_SEND_USER?.trim() || "testuser";
const topicId = process.env.SMOKE_TOPIC_ID?.trim() || "topic-local-1";
const text = process.env.SMOKE_TEXT?.trim() || "你好";

if (!process.env.INTERNAL_CHAT_ASSISTANT_ID?.trim() || !process.env.INTERNAL_CHAT_ASSISTANT_SECRET?.trim()) {
  console.error("Set INTERNAL_CHAT_ASSISTANT_ID and INTERNAL_CHAT_ASSISTANT_SECRET (non-empty) before running.");
  process.exit(1);
}

const p = createBridgeProvider();
await p.initialize({
  outbound: {
    emitOutboundMessage: async () => ({ applied: true }),
  },
});

const title = JSON.stringify({
  welink: { sendUserAccount: sendUser, topicId },
});
console.error("[smoke] createSession with welink title …");
const { toolSessionId } = await p.createSession({ traceId: "smoke-trace", title });
console.error("[smoke] toolSessionId =", toolSessionId);

console.error("[smoke] runMessage …");
const run = await p.runMessage({
  traceId: "smoke-trace",
  runId: `smoke-run-${Date.now()}`,
  toolSessionId,
  text,
});

for await (const f of run.facts) {
  if (f.type === "text.delta") {
    process.stdout.write(f.content);
  } else {
    console.error("\n[smoke] fact:", f.type);
  }
}
console.error("");
const terminal = await run.result();
console.error("[smoke] result()", terminal);
if (terminal.outcome !== "completed") {
  process.exit(1);
}
