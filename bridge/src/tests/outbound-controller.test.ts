import test from "node:test";
import assert from "node:assert/strict";
import { ConcurrencyGuard } from "../runtime/concurrency-guard.js";
import { OutboundController } from "../runtime/outbound-controller.js";
import { ProviderCommandError } from "../spi/errors.js";
import type { ProviderFact } from "../spi/types.js";

test("OutboundController rejects second outbound while first active", async () => {
  const guard = new ConcurrencyGuard();
  const ob = new OutboundController(guard);
  let consumed = 0;
  ob.setContext({
    outbound: {
      emitOutboundMessage: async () => {
        consumed += 1;
        await new Promise((r) => setTimeout(r, 50));
        return { applied: true as const };
      },
    },
  });
  const facts = async function* (): AsyncIterable<ProviderFact> {
    yield { type: "message.start", toolSessionId: "s1", messageId: "m1" };
  };
  const p1 = ob.emit({
    toolSessionId: "s1",
    messageId: "m1",
    trigger: "system",
    facts: facts(),
  });
  await assert.rejects(
    () =>
      ob.emit({
        toolSessionId: "s1",
        messageId: "m2",
        trigger: "system",
        facts: facts(),
      }),
    (e: unknown) => e instanceof ProviderCommandError && e.code === "invalid_input",
  );
  await p1;
  assert.equal(consumed, 1);
});
