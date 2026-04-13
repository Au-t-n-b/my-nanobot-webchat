import test from "node:test";
import assert from "node:assert/strict";

import { shouldSuppressAutoGuide } from "../lib/dashboardAutoGuidePolicy.js";

test("completed modeling simulation module is allowed to replay guide", () => {
  assert.equal(shouldSuppressAutoGuide("modeling_simulation_workbench", "completed"), false);
});

test("completed non-modeling module still suppresses auto guide", () => {
  assert.equal(shouldSuppressAutoGuide("intelligent_analysis_workbench", "completed"), true);
});

test("running modules always suppress auto guide", () => {
  assert.equal(shouldSuppressAutoGuide("modeling_simulation_workbench", "running"), true);
});
