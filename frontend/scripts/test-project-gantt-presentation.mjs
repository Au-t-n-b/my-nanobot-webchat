import test from "node:test";
import assert from "node:assert/strict";

import {
  formatEstimatedDurationLabel,
  formatPlanningStatusLabel,
  formatProjectGanttMetaLabel,
  getProjectGanttEstimatedDays,
} from "../lib/projectGantt/presentation.js";

test("formatEstimatedDurationLabel formats inclusive day counts", () => {
  assert.equal(formatEstimatedDurationLabel(5), "预计 5 天");
  assert.equal(formatEstimatedDurationLabel(0), "预计 1 天");
});

test("formatPlanningStatusLabel marks placeholder modules", () => {
  assert.equal(formatPlanningStatusLabel(true), "规划中");
  assert.equal(formatPlanningStatusLabel(false), "");
});

test("formatProjectGanttMetaLabel combines planning and duration labels", () => {
  assert.equal(formatProjectGanttMetaLabel({ estimatedDays: 4, isPlaceholder: true }), "规划中 · 预计 4 天");
  assert.equal(formatProjectGanttMetaLabel({ estimatedDays: 6, isPlaceholder: false }), "预计 6 天");
});

test("getProjectGanttEstimatedDays keeps a stable minimum duration", () => {
  assert.equal(getProjectGanttEstimatedDays(0), 3);
  assert.equal(getProjectGanttEstimatedDays(2), 3);
  assert.equal(getProjectGanttEstimatedDays(7), 7);
});
