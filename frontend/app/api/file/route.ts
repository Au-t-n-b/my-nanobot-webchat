/**
 * GET /api/file?path=<absolute-or-relative-path>
 *
 * Local Next.js implementation that mirrors the Python AGUI /api/file behaviour:
 *  - Absolute paths  → serve the file as-is (same as Python resolve_file_target)
 *  - Relative paths  → resolve under NANOBOT_AGUI_WORKSPACE (or ~/.nanobot/workspace)
 *
 * This Next.js route takes priority over the /api/:path* rewrite in next.config.ts,
 * so file serving works even when the Python backend is not reachable.
 */

import fs from "fs";
import path from "path";
import os from "os";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { findPreviewFileFallback, registerKnownFilePath } from "@/lib/fileResolver";

const MIME: Record<string, string> = {
  // text
  txt: "text/plain; charset=utf-8",
  md: "text/plain; charset=utf-8",
  markdown: "text/plain; charset=utf-8",
  mmd: "text/plain; charset=utf-8",
  mermaid: "text/plain; charset=utf-8",
  json: "application/json; charset=utf-8",
  yaml: "text/plain; charset=utf-8",
  yml: "text/plain; charset=utf-8",
  toml: "text/plain; charset=utf-8",
  csv: "text/csv; charset=utf-8",
  ts: "text/plain; charset=utf-8",
  tsx: "text/plain; charset=utf-8",
  js: "text/javascript; charset=utf-8",
  jsx: "text/javascript; charset=utf-8",
  py: "text/plain; charset=utf-8",
  rs: "text/plain; charset=utf-8",
  sh: "text/plain; charset=utf-8",
  css: "text/css; charset=utf-8",
  html: "text/html; charset=utf-8",
  htm: "text/html; charset=utf-8",
  xml: "application/xml; charset=utf-8",
  ini: "text/plain; charset=utf-8",
  log: "text/plain; charset=utf-8",
  // binary
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  svg: "image/svg+xml",
  pdf: "application/pdf",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xls: "application/vnd.ms-excel",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

function getWorkspaceRoot(): string {
  const env = process.env.NANOBOT_AGUI_WORKSPACE?.trim();
  if (env) return path.resolve(env.replace(/^~/, os.homedir()));
  return path.join(os.homedir(), ".nanobot", "workspace");
}

function getMime(filePath: string): string {
  const ext = filePath.split(".").pop()?.toLowerCase() ?? "";
  return MIME[ext] ?? "application/octet-stream";
}

function normalizeQueryPath(raw: string): string {
  // backslashes → forward slashes (mirrors Python normalize_file_query)
  return raw.replace(/\\/g, "/").trim();
}

function resolveFilePath(normalized: string): string {
  // absolute path check: has drive letter (Windows) or starts with /
  const isAbsolute =
    /^[A-Za-z]:\//.test(normalized) || normalized.startsWith("/");

  if (isAbsolute) {
    return path.resolve(normalized);
  }

  // relative: resolve under workspace
  const workspace = getWorkspaceRoot();
  const resolved = path.resolve(workspace, normalized);
  // security: ensure it stays under workspace
  if (!resolved.startsWith(workspace)) {
    throw new Error("path escapes workspace");
  }
  return resolved;
}

export async function GET(req: NextRequest) {
  const raw = req.nextUrl.searchParams.get("path");

  if (!raw?.trim()) {
    return NextResponse.json({ detail: "path query parameter is required" }, { status: 400 });
  }

  let filePath: string;
  try {
    filePath = resolveFilePath(normalizeQueryPath(raw));
  } catch (e) {
    return NextResponse.json({ detail: String(e) }, { status: 400 });
  }

  // Primary lookup
  let exists = false;
  try { exists = fs.statSync(filePath).isFile(); } catch { /* not found */ }

  // Fallbacks:
  // 1. old behavior: bare filename under workspace
  // 2. new behavior: search likely external skill output roots for bare filenames
  //    and relative Output/RunTime/Input paths
  if (!exists) {
    const normalized = normalizeQueryPath(raw);
    const isBareFilename = !normalized.includes("/") && !normalized.includes("\\");
    const workspace = getWorkspaceRoot();
    const found = findPreviewFileFallback(normalized, {
      workspaceRoot: workspace,
      cwd: process.cwd(),
    });
    if (found && (isBareFilename || normalized.startsWith("Output/") || normalized.startsWith("RunTime/") || normalized.startsWith("Input/") || normalized.startsWith("Start/"))) {
      filePath = found;
      // Cache the resolved path so the next request for this filename is instant
      registerKnownFilePath(normalized, found, workspace);
    }
  }

  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) {
      return NextResponse.json({ detail: "not a file" }, { status: 404 });
    }
  } catch {
    return NextResponse.json({ detail: "file not found" }, { status: 404 });
  }

  try {
    const body = fs.readFileSync(filePath);
    const mime = getMime(filePath);
    return new NextResponse(body, {
      status: 200,
      headers: { "Content-Type": mime },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("EACCES") || msg.includes("permission")) {
      return NextResponse.json({ detail: "permission denied" }, { status: 403 });
    }
    return NextResponse.json({ detail: msg }, { status: 500 });
  }
}
