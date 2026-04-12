import test from "node:test";
import assert from "node:assert/strict";

import { normalizeDonutSegments } from "../lib/sduiDonutChart.js";

test("normalizeDonutSegments returns an empty array when segments are missing", () => {
  assert.deepEqual(normalizeDonutSegments(undefined), []);
  assert.deepEqual(normalizeDonutSegments(null), []);
});

test("normalizeDonutSegments keeps only positive finite values", () => {
  const actual = normalizeDonutSegments([
    { label: "valid-a", value: 2 },
    { label: "zero", value: 0 },
    { label: "nan", value: Number.NaN },
    { label: "negative", value: -1 },
    { label: "valid-b", value: 3 },
  ]);

  assert.deepEqual(actual, [
    { label: "valid-a", value: 2 },
    { label: "valid-b", value: 3 },
  ]);
});
