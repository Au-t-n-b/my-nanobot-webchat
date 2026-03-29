import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const PREFERRED_DIRS = new Set(["output", "runtime", "input", "start"]);
const DEFAULT_MAX_DEPTH = 7;

function normalizeSlashes(value) {
  return value.replace(/\\/g, "/");
}

function uniqueExistingDirs(values) {
  const seen = new Set();
  const out = [];
  for (const raw of values) {
    if (!raw) continue;
    const full = path.resolve(raw);
    const key = normalizeSlashes(full).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    try {
      if (fs.statSync(full).isDirectory()) out.push(full);
    } catch {
      // ignore missing roots
    }
  }
  return out;
}

function getWindowsDriveRoots() {
  if (process.platform !== "win32") return [];
  const roots = [];
  for (let code = 67; code <= 90; code += 1) {
    const drive = `${String.fromCharCode(code)}:\\`;
    if (fs.existsSync(drive)) roots.push(drive);
  }
  return roots;
}

function buildSearchRoots({ workspaceRoot, cwd, extraRoots = [] }) {
  const envRoots = (process.env.NANOBOT_AGUI_FILE_SEARCH_ROOTS ?? "")
    .split(path.delimiter)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.replace(/^~/, os.homedir()));

  return uniqueExistingDirs([
    workspaceRoot,
    workspaceRoot ? path.dirname(workspaceRoot) : "",
    cwd,
    cwd ? path.dirname(cwd) : "",
    os.homedir(),
    ...extraRoots,
    ...envRoots,
    ...getWindowsDriveRoots(),
  ]);
}

function findByExactSuffix(suffixPath, root, depth = 0, maxDepth = DEFAULT_MAX_DEPTH) {
  if (depth > maxDepth) return null;
  let entries = [];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }

  const wanted = normalizeSlashes(suffixPath).toLowerCase();
  for (const entry of entries) {
    const full = path.join(root, entry.name);
    if (entry.isFile()) {
      if (normalizeSlashes(full).toLowerCase().endsWith(`/${wanted}`)) return full;
      continue;
    }
    if (entry.isDirectory()) {
      const found = findByExactSuffix(suffixPath, full, depth + 1, maxDepth);
      if (found) return found;
    }
  }
  return null;
}

function findInPreferredDirs(fileName, root, depth = 0, maxDepth = DEFAULT_MAX_DEPTH) {
  if (depth > maxDepth) return null;
  let entries = [];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const full = path.join(root, entry.name);
    const lower = entry.name.toLowerCase();

    if (PREFERRED_DIRS.has(lower)) {
      const direct = path.join(full, fileName);
      try {
        if (fs.statSync(direct).isFile()) return direct;
      } catch {
        // continue deeper
      }
      const foundInDir = findByFileName(fileName, full, 0, 2);
      if (foundInDir) return foundInDir;
    }

    const found = findInPreferredDirs(fileName, full, depth + 1, maxDepth);
    if (found) return found;
  }
  return null;
}

function findByFileName(fileName, root, depth = 0, maxDepth = 6) {
  if (depth > maxDepth) return null;
  let entries = [];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }

  for (const entry of entries) {
    const full = path.join(root, entry.name);
    if (entry.isFile() && entry.name.toLowerCase() === fileName.toLowerCase()) return full;
    if (entry.isDirectory()) {
      const found = findByFileName(fileName, full, depth + 1, maxDepth);
      if (found) return found;
    }
  }
  return null;
}

/**
 * Find generated preview files that live outside the AGUI workspace.
 * Supports:
 * - bare filenames: `工勘报告.docx`
 * - relative skill paths: `Output/工勘报告.docx`, `RunTime/定制工勘表.xlsx`
 */
export function findPreviewFileFallback(rawPath, options) {
  const normalized = normalizeSlashes(rawPath || "").trim().replace(/^\.?\//, "");
  if (!normalized) return null;

  const roots = buildSearchRoots(options);
  const hasSeparator = normalized.includes("/");

  for (const root of roots) {
    if (hasSeparator) {
      const found = findByExactSuffix(normalized, root);
      if (found) return found;
      continue;
    }

    const preferred = findInPreferredDirs(normalized, root);
    if (preferred) return preferred;

    const generic = findByFileName(normalized, root);
    if (generic) return generic;
  }

  return null;
}

