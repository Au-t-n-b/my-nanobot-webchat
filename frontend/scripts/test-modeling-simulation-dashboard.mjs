import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const DASHBOARD_PATH = new URL("../../templates/modeling_simulation_workbench/data/dashboard.json", import.meta.url);

test("modeling simulation dashboard embeds the designated access page", async () => {
  const raw = await readFile(DASHBOARD_PATH, "utf8");
  const dashboard = JSON.parse(raw);
  const embeddedWeb = dashboard.root.children.find((node) => node?.id === "embedded-modeling-access");

  assert.ok(embeddedWeb, "expected embedded web node to exist");
  assert.equal(embeddedWeb.src, "http://100.102.191.17/access.html?v=2.19.9");
});
