import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const overviewPath = path.join(__dirname, "../components/dashboard/ProjectOverview.tsx");
const overviewSource = fs.readFileSync(overviewPath, "utf8");

test("ProjectOverview keeps module access inside the shared module cards instead of duplicate entry rows", () => {
  assert.equal(overviewSource.includes("进入作业管理大盘"), false);
  assert.equal(overviewSource.includes("进入智能分析工作台"), false);
  assert.equal(overviewSource.includes("进入建模仿真模块"), false);
  assert.equal(overviewSource.includes("进入智慧工勘模块"), false);
  assert.match(overviewSource, /打开大盘/);
});
