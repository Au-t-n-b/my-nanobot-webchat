import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// ── constants ─────────────────────────────────────────────────────────────────

const PREFERRED_DIRS = new Set(["output", "runtime", "input", "start"]);

// Skip these directories entirely — they will never contain user-generated files
// and can be enormous (system dirs, package caches, version-control metadata).
const SKIP_DIRS = new Set([
  "windows", "system32", "syswow64", "winsxs", "winnt",
  "program files", "program files (x86)",
  "$recycle.bin", "programdata",
  "node_modules", ".git", ".svn", ".hg",
  "__pycache__", ".cache", ".npm", ".yarn",
  "appdata", "application data",
]);

// How deep to search depending on where we start.
// Drive roots (C:\, D:\) need a lower cap to avoid minutes-long scanning.
const DEPTH_WORKSPACE = 7; // inside ~/.nanobot/workspace and siblings → thorough
const DEPTH_HOME      = 6; // user home directory
const DEPTH_CWD       = 5; // process.cwd() and its parent
const DEPTH_DRIVE     = 4; // raw drive roots (C:\, D:\) → shallow

// Search results are cached in memory for the process lifetime.
// Key = rawPath + "|" + workspaceRoot. Value = resolved absolute path.
const _cache = new Map();

// Hard deadline per findPreviewFileFallback call (ms).
const DEADLINE_MS = 3_000;

// ── helpers ───────────────────────────────────────────────────────────────────

function normalizeSlashes(value) {
  return value.replace(/\\/g, "/");
}

function shouldSkip(dirName) {
  return SKIP_DIRS.has(dirName.toLowerCase());
}

function uniqueExistingDirs(values) {
  const seen = new Set();
  const out = [];
  for (const raw of values) {
    if (!raw) continue;
    let full;
    try { full = path.resolve(raw); } catch { continue; }
    const key = normalizeSlashes(full).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    try {
      if (fs.statSync(full).isDirectory()) out.push(full);
    } catch { /* skip missing */ }
  }
  return out;
}

function getWindowsDriveRoots() {
  if (process.platform !== "win32") return [];
  const roots = [];
  for (let code = 67; code <= 90; code += 1) {
    const drive = `${String.fromCharCode(code)}:\\`;
    try { if (fs.statSync(drive).isDirectory()) roots.push(drive); } catch { /* no drive */ }
  }
  return roots;
}

/**
 * Build the ordered list of [root, maxDepth] pairs to search.
 * Roots closer to the user's project are first and searched more deeply.
 */
function buildSearchRoots({ workspaceRoot, cwd, extraRoots = [] }) {
  const envRoots = (process.env.NANOBOT_AGUI_FILE_SEARCH_ROOTS ?? "")
    .split(path.delimiter)
    .filter(Boolean)
    .map((s) => s.trim().replace(/^~/, os.homedir()));

  const home = os.homedir();
  const workspaceParent = workspaceRoot ? path.dirname(workspaceRoot) : "";
  const cwdParent = cwd ? path.dirname(cwd) : "";

  // Assign depth per root category
  const withDepth = (dirs, depth) => dirs.map((d) => [d, depth]);

  const candidates = [
    // env override roots — most specific, search deeply
    ...withDepth(uniqueExistingDirs(envRoots), DEPTH_WORKSPACE),
    // workspace and its parent
    ...withDepth(uniqueExistingDirs([workspaceRoot, workspaceParent]), DEPTH_WORKSPACE),
    // extra roots provided by caller (test helpers, etc.)
    ...withDepth(uniqueExistingDirs(extraRoots), DEPTH_WORKSPACE),
    // process cwd and its parent
    ...withDepth(uniqueExistingDirs([cwd, cwdParent]), DEPTH_CWD),
    // user home
    ...withDepth(uniqueExistingDirs([home]), DEPTH_HOME),
    // drive roots — last resort, shallow scan only
    ...withDepth(uniqueExistingDirs(getWindowsDriveRoots()), DEPTH_DRIVE),
  ];

  // De-duplicate while preserving order; keep the first (deepest) depth seen.
  const seen = new Set();
  const result = [];
  for (const [dir, depth] of candidates) {
    const key = normalizeSlashes(dir).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push([dir, depth]);
  }
  return result;
}

// ── core search functions ─────────────────────────────────────────────────────

/**
 * Search for a file whose path ends with `suffixPath` (e.g. "Output/工勘报告.docx").
 * Returns the first match, or null. Aborts when `deadline` timestamp is reached.
 */
function findByExactSuffix(suffixPath, root, deadline, depth = 0, maxDepth = DEPTH_WORKSPACE) {
  if (depth > maxDepth || Date.now() > deadline) return null;
  let entries = [];
  try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch { return null; }

  const wanted = normalizeSlashes(suffixPath).toLowerCase();
  for (const entry of entries) {
    if (Date.now() > deadline) return null;
    const full = path.join(root, entry.name);
    if (entry.isFile()) {
      if (normalizeSlashes(full).toLowerCase().endsWith(`/${wanted}`)) return full;
      continue;
    }
    if (entry.isDirectory() && !shouldSkip(entry.name)) {
      const found = findByExactSuffix(suffixPath, full, deadline, depth + 1, maxDepth);
      if (found) return found;
    }
  }
  return null;
}

/**
 * Search for `fileName` inside preferred skill output dirs (Output, RunTime, Input, Start)
 * before doing a generic scan. Returns the first match, or null.
 */
function findInPreferredDirs(fileName, root, deadline, depth = 0, maxDepth = DEPTH_WORKSPACE) {
  if (depth > maxDepth || Date.now() > deadline) return null;
  let entries = [];
  try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch { return null; }

  for (const entry of entries) {
    if (Date.now() > deadline) return null;
    if (!entry.isDirectory() || shouldSkip(entry.name)) continue;
    const full = path.join(root, entry.name);
    const lower = entry.name.toLowerCase();

    if (PREFERRED_DIRS.has(lower)) {
      // Direct lookup first (O(1) if file exists)
      const direct = path.join(full, fileName);
      try { if (fs.statSync(direct).isFile()) return direct; } catch { /* not here */ }
      // Shallow scan inside the preferred dir (depth 2)
      const foundInDir = findByFileName(fileName, full, deadline, 0, 2);
      if (foundInDir) return foundInDir;
    }

    const found = findInPreferredDirs(fileName, full, deadline, depth + 1, maxDepth);
    if (found) return found;
  }
  return null;
}

/**
 * Generic recursive filename search.
 */
function findByFileName(fileName, root, deadline, depth = 0, maxDepth = 6) {
  if (depth > maxDepth || Date.now() > deadline) return null;
  let entries = [];
  try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch { return null; }

  for (const entry of entries) {
    if (Date.now() > deadline) return null;
    const full = path.join(root, entry.name);
    if (entry.isFile() && entry.name.toLowerCase() === fileName.toLowerCase()) return full;
    if (entry.isDirectory() && !shouldSkip(entry.name)) {
      const found = findByFileName(fileName, full, deadline, depth + 1, maxDepth);
      if (found) return found;
    }
  }
  return null;
}

// ── public API ────────────────────────────────────────────────────────────────

/**
 * Find generated preview files that live outside the AGUI workspace.
 * Results are cached in-process so repeated requests for the same file are instant.
 *
 * Supports:
 * - bare filenames:       `工勘报告.docx`
 * - relative skill paths: `Output/工勘报告.docx`, `RunTime/定制工勘表.xlsx`
 */
export function findPreviewFileFallback(rawPath, options) {
  const normalized = normalizeSlashes(rawPath || "").trim().replace(/^\.?\//, "");
  if (!normalized) return null;

  const cacheKey = `${normalized}|${options?.workspaceRoot ?? ""}`;
  if (_cache.has(cacheKey)) return _cache.get(cacheKey);

  const roots = buildSearchRoots(options ?? {});
  const hasSeparator = normalized.includes("/");
  const deadline = Date.now() + DEADLINE_MS;

  let result = null;
  for (const [root, maxDepth] of roots) {
    if (Date.now() > deadline) break;

    if (hasSeparator) {
      result = findByExactSuffix(normalized, root, deadline, 0, maxDepth);
    } else {
      result = findInPreferredDirs(normalized, root, deadline, 0, maxDepth)
        ?? findByFileName(normalized, root, deadline, 0, maxDepth);
    }

    if (result) break;
  }

  if (result) _cache.set(cacheKey, result);
  return result;
}

/**
 * Manually register a known file path so future requests for that filename
 * skip the search entirely. Call this after a successful lookup from absolute path.
 */
export function registerKnownFilePath(rawPath, absolutePath, workspaceRoot = "") {
  const normalized = normalizeSlashes(rawPath || "").trim().replace(/^\.?\//, "");
  if (normalized && absolutePath) {
    _cache.set(`${normalized}|${workspaceRoot}`, absolutePath);
  }
}
