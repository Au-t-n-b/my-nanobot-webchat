import test from "node:test";
import assert from "node:assert/strict";
import { ConcurrencyGuard } from "../runtime/concurrency-guard.js";
import { ProviderCommandError } from "../spi/errors.js";

test("ConcurrencyGuard rejects nested run on same session", () => {
  const g = new ConcurrencyGuard();
  g.beginRun("sess_a");
  assert.throws(
    () => g.beginRun("sess_a"),
    (e: unknown) => e instanceof ProviderCommandError && e.code === "invalid_input",
  );
  g.endRun("sess_a");
  g.beginRun("sess_a");
  g.endRun("sess_a");
});
