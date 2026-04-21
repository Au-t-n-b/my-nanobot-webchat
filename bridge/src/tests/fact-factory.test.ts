import test from "node:test";
import assert from "node:assert/strict";
import { DefaultFactFactory } from "../facts/fact-factory.js";
import type { InternalStreamChunk } from "../adapters/internal-chat-types.js";

async function* chunks(...items: InternalStreamChunk[]): AsyncIterable<InternalStreamChunk> {
  for (const c of items) yield c;
}

test("FactFactory emits message.start then deltas then done facts", async () => {
  const factory = new DefaultFactFactory();
  const state: import("../facts/fact-factory.js").ExecutionState = {};
  const out: string[] = [];
  for await (const f of factory.stream(chunks({ kind: "text", text: "hi" }, { kind: "done" }), {
    toolSessionId: "sess_x",
    messageId: "msg_x",
    partId: "part_x",
    state,
  })) {
    out.push(f.type);
  }
  assert.deepEqual(out, ["message.start", "text.delta", "text.done", "message.done"]);
  assert.equal(state.failed, undefined);
  assert.equal(state.aborted, undefined);
});

test("FactFactory skips empty text chunks", async () => {
  const factory = new DefaultFactFactory();
  const state: import("../facts/fact-factory.js").ExecutionState = {};
  let deltas = 0;
  for await (const f of factory.stream(chunks({ kind: "text", text: "" }, { kind: "text", text: "a" }, { kind: "done" }), {
    toolSessionId: "sess_x",
    messageId: "msg_x",
    partId: "part_x",
    state,
  })) {
    if (f.type === "text.delta") deltas += 1;
  }
  assert.equal(deltas, 1);
});
