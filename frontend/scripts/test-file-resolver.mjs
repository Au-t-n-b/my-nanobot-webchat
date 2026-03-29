import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { findPreviewFileFallback } from "../lib/fileResolver.js";

function makeTempTree() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "nanobot-file-resolver-"));
  const workspace = path.join(root, "workspace");
  const external = path.join(root, "Skills", "智慧工勘Skill");
  fs.mkdirSync(path.join(workspace, "docs"), { recursive: true });
  fs.mkdirSync(path.join(external, "RunTime"), { recursive: true });
  fs.mkdirSync(path.join(external, "Output"), { recursive: true });
  fs.writeFileSync(path.join(workspace, "docs", "readme.txt"), "ok");
  fs.writeFileSync(path.join(external, "RunTime", "定制工勘表.xlsx"), "xlsx");
  fs.writeFileSync(path.join(external, "Output", "工勘报告.docx"), "docx");
  return { root, workspace, external };
}

test("finds bare generated filenames outside workspace", () => {
  const { root, workspace } = makeTempTree();
  const found = findPreviewFileFallback("定制工勘表.xlsx", {
    workspaceRoot: workspace,
    cwd: root,
    extraRoots: [root],
  });
  assert.equal(found, path.join(root, "Skills", "智慧工勘Skill", "RunTime", "定制工勘表.xlsx"));
});

test("finds relative Output/RunTime paths outside workspace", () => {
  const { root, workspace } = makeTempTree();
  const found = findPreviewFileFallback("Output/工勘报告.docx", {
    workspaceRoot: workspace,
    cwd: root,
    extraRoots: [root],
  });
  assert.equal(found, path.join(root, "Skills", "智慧工勘Skill", "Output", "工勘报告.docx"));
});

