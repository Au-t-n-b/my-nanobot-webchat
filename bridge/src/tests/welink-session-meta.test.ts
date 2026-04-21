import test from "node:test";
import assert from "node:assert/strict";
import { parseWelinkCreateSessionTitle, welinkThreadId } from "../adapters/welink-session-meta.js";
import { ProviderCommandError } from "../spi/errors.js";

test("parseWelinkCreateSessionTitle accepts valid JSON title", () => {
  const title = JSON.stringify({ welink: { sendUserAccount: "u1", topicId: 42 } });
  const m = parseWelinkCreateSessionTitle(title);
  assert.equal(m.sendUserAccount, "u1");
  assert.equal(m.topicId, 42);
  assert.match(welinkThreadId(m), /^welink:u1:42$/);
});

test("parseWelinkCreateSessionTitle rejects missing title", () => {
  assert.throws(
    () => parseWelinkCreateSessionTitle(undefined),
    (e: unknown) => e instanceof ProviderCommandError && e.code === "invalid_input",
  );
});
