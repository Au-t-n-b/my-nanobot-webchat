"use client";

import * as XLSX from "xlsx";
import mammoth from "mammoth/mammoth.browser.js";
import mermaid from "mermaid";
import type { PreviewKind } from "@/lib/previewKind";
import type { PreviewParser, PreviewResolution } from "./previewTypes";

export type TextPayload = { type: "text"; text: string };
export type MarkdownPayload = { type: "markdown"; text: string };
export type HtmlPayload = { type: "html"; html: string };
export type TablePayload = { type: "table"; rows: string[][] };
export type MermaidPayload = { type: "mermaid"; svg: string; source: string };
export type DataGridPayload = {
  type: "datagrid";
  /** 原始源码（用于源码模式） */
  sourceText: string;
  /** 表格模式数据 */
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, unknown>>;
  /** 截断标识与提示 */
  isTruncated: boolean;
  totalRows?: number;
  totalColumns?: number;
  warning?: string;
};

export type XlsxMultiPayload = {
  type: "xlsx";
  sheets: Array<{
    name: string;
    rows: string[][];
    isTruncated: boolean;
    totalRows?: number;
    totalColumns?: number;
  }>;
};

export type PreviewPayload =
  | TextPayload
  | MarkdownPayload
  | HtmlPayload
  | TablePayload
  | MermaidPayload
  | DataGridPayload
  | XlsxMultiPayload
  | { type: "none" };

const MAX_PARSE_BYTES = 5 * 1024 * 1024; // 5MB
const MAX_GRID_ROWS = 1000;
const MAX_GRID_COLS = 50;

async function fetchOk(resolution: PreviewResolution): Promise<Response> {
  if (!resolution.url) throw new Error("missing preview url");
  const res = await fetch(resolution.url);
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(t || `HTTP ${res.status}`);
  }
  return res;
}

function extFromPath(path: string): string {
  const i = path.lastIndexOf(".");
  return i >= 0 ? path.slice(i + 1).toLowerCase() : "";
}

function countNewlines(text: string): number {
  let n = 0;
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) n++;
  return n;
}

function hardCutColumns(cols: string[]): string[] {
  return cols.slice(0, MAX_GRID_COLS);
}

function buildColumnsFromHeader(header: string[]): Array<{ key: string; label: string }> {
  const safe = hardCutColumns(header).map((h, idx) => (h ?? "").trim() || `col_${idx + 1}`);
  const dedup = new Map<string, number>();
  const labels = safe.map((l) => {
    const k = l;
    const n = (dedup.get(k) ?? 0) + 1;
    dedup.set(k, n);
    return n === 1 ? l : `${l}_${n}`;
  });
  return labels.map((label, i) => ({ key: `c${i + 1}`, label }));
}

function rowsToRecords(columns: Array<{ key: string; label: string }>, rows: string[][]): Array<Record<string, unknown>> {
  return rows.map((r) => {
    const obj: Record<string, unknown> = {};
    for (let i = 0; i < columns.length; i++) obj[columns[i]!.key] = r[i] ?? "";
    return obj;
  });
}

function parseCsvBasic(text: string): { header: string[]; body: string[][]; isTruncated: boolean; totalRows?: number; totalColumns?: number } {
  // Minimal CSV parser with quote support, good enough for preview.
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;
  let i = 0;
  let bodyTruncated = false;

  const pushCell = () => {
    row.push(cell);
    cell = "";
  };
  const pushRow = () => {
    // Drop trailing empty row caused by final newline
    if (rows.length < MAX_GRID_ROWS + 1) rows.push(row);
    else bodyTruncated = true;
    row = [];
  };

  while (i < text.length) {
    const ch = text[i]!;
    if (ch === "\"") {
      if (inQuotes && text[i + 1] === "\"") {
        cell += "\"";
        i += 2;
        continue;
      }
      inQuotes = !inQuotes;
      i++;
      continue;
    }
    if (!inQuotes && (ch === "," || ch === "\t")) {
      pushCell();
      i++;
      continue;
    }
    if (!inQuotes && (ch === "\n" || ch === "\r")) {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      pushCell();
      pushRow();
      i++;
      continue;
    }
    cell += ch;
    i++;
  }
  pushCell();
  if (row.length > 1 || row[0] !== "") pushRow();

  const header = rows[0] ?? [];
  const body = rows.slice(1, MAX_GRID_ROWS + 1);
  const totalRows = rows.length > 0 ? rows.length - 1 : 0;
  const totalColumns = header.length;
  const isTruncated = bodyTruncated || body.length >= MAX_GRID_ROWS;
  return { header, body, isTruncated, totalRows, totalColumns };
}

function jsonToGrid(value: unknown): { columns: Array<{ key: string; label: string }>; rows: Array<Record<string, unknown>>; isTruncated: boolean; totalRows?: number; totalColumns?: number } {
  if (Array.isArray(value)) {
    const totalRows = value.length;
    const slice = value.slice(0, MAX_GRID_ROWS);
    const isTruncated = totalRows > slice.length;

    // Array of objects → union keys (capped)
    const keySet: string[] = [];
    const keySeen = new Set<string>();
    for (const item of slice) {
      if (!item || typeof item !== "object" || Array.isArray(item)) continue;
      for (const k of Object.keys(item as Record<string, unknown>)) {
        if (keySeen.has(k)) continue;
        keySeen.add(k);
        keySet.push(k);
        if (keySet.length >= MAX_GRID_COLS) break;
      }
      if (keySet.length >= MAX_GRID_COLS) break;
    }

    const columns =
      keySet.length > 0
        ? keySet.map((k, idx) => ({ key: `c${idx + 1}`, label: k }))
        : [{ key: "c1", label: "value" }];

    const rows = slice.map((item) => {
      const obj: Record<string, unknown> = {};
      if (keySet.length > 0 && item && typeof item === "object" && !Array.isArray(item)) {
        keySet.forEach((k, idx) => {
          obj[`c${idx + 1}`] = (item as Record<string, unknown>)[k];
        });
      } else {
        obj["c1"] = item;
      }
      return obj;
    });

    return { columns, rows, isTruncated, totalRows, totalColumns: columns.length };
  }

  if (value && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    const totalRows = entries.length;
    const slice = entries.slice(0, MAX_GRID_ROWS);
    const isTruncated = totalRows > slice.length;
    const columns = [
      { key: "c1", label: "key" },
      { key: "c2", label: "value" },
    ];
    const rows = slice.map(([k, v]) => ({ c1: k, c2: v }));
    return { columns, rows, isTruncated, totalRows, totalColumns: 2 };
  }

  return {
    columns: [{ key: "c1", label: "value" }],
    rows: [{ c1: value }],
    isTruncated: false,
    totalRows: 1,
    totalColumns: 1,
  };
}

async function fetchTextWithSizeGuard(resolution: PreviewResolution): Promise<{ text: string; tooLarge: boolean; warning?: string }> {
  const res = await fetchOk(resolution);
  const contentLength = Number(res.headers.get("content-length") ?? "");
  if (Number.isFinite(contentLength) && contentLength > MAX_PARSE_BYTES) {
    return {
      text: "",
      tooLarge: true,
      warning: `文件过大（>${(MAX_PARSE_BYTES / (1024 * 1024)).toFixed(0)}MB），已降级为源码预览。`,
    };
  }
  const text = await res.text();
  if (text.length > MAX_PARSE_BYTES) {
    return {
      text,
      tooLarge: true,
      warning: `文件过大（>${(MAX_PARSE_BYTES / (1024 * 1024)).toFixed(0)}MB），已降级为源码预览。`,
    };
  }
  return { text, tooLarge: false };
}

const parseText: PreviewParser<TextPayload | MarkdownPayload | DataGridPayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const text = await res.text();
  if (resolution.kind === "md") return { type: "markdown", text };

  const ext = extFromPath(resolution.path);
  if (ext !== "json" && ext !== "csv") return { type: "text", text };

  // File-size guard (best-effort) – for text we already have it; keep behavior safe.
  if (text.length > MAX_PARSE_BYTES) return { type: "text", text };

  if (ext === "csv") {
    const { header, body, isTruncated, totalRows, totalColumns } = parseCsvBasic(text);
    const columns = buildColumnsFromHeader(header);
    const bodyCut = body.map((r) => hardCutColumns(r));
    const rows = rowsToRecords(columns, bodyCut);
    return {
      type: "datagrid",
      sourceText: text,
      columns,
      rows,
      isTruncated: isTruncated || (totalColumns ?? 0) > MAX_GRID_COLS,
      totalRows,
      totalColumns,
      warning:
        isTruncated || (totalColumns ?? 0) > MAX_GRID_COLS
          ? `⚠️ 预览已截断：当前文件过大，仅展示前 ${MAX_GRID_ROWS} 行 / ${MAX_GRID_COLS} 列。请下载原文件查看完整数据。`
          : undefined,
    };
  }

  // JSON
  try {
    const parsed = JSON.parse(text) as unknown;
    const grid = jsonToGrid(parsed);
    return {
      type: "datagrid",
      sourceText: text,
      columns: grid.columns,
      rows: grid.rows,
      isTruncated: grid.isTruncated || (grid.totalColumns ?? 0) > MAX_GRID_COLS,
      totalRows: grid.totalRows,
      totalColumns: grid.totalColumns,
      warning:
        grid.isTruncated
          ? `⚠️ 预览已截断：当前文件过大，仅展示前 ${MAX_GRID_ROWS} 行。请下载原文件查看完整数据。`
          : undefined,
    };
  } catch {
    return { type: "text", text };
  }
};

const parseMermaid: PreviewParser<MermaidPayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const source = await res.text();
  // 与旧逻辑保持一致：严格模式、dark 主题
  mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
  const id = `mmd-${stableMermaidId(resolution.path)}`;
  const { svg } = await mermaid.render(id, source);
  return { type: "mermaid", svg, source };
};

const parseXlsx: PreviewParser<XlsxMultiPayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const buf = await res.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });
  const names = wb.SheetNames ?? [];
  if (!names.length) throw new Error("empty workbook");
  const sheets = names.map((name) => {
    const sheet = wb.Sheets[name];
    const allRows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, defval: "" }) as string[][];
    const totalRows = allRows.length;
    const totalColumns = Math.max(0, ...allRows.map((r) => r.length));
    const isTruncated = totalRows > MAX_GRID_ROWS || totalColumns > MAX_GRID_COLS;
    const rows = allRows.slice(0, MAX_GRID_ROWS).map((r) => r.slice(0, MAX_GRID_COLS));
    return { name, rows, isTruncated, totalRows, totalColumns };
  });
  return { type: "xlsx", sheets };
};

const parseDocx: PreviewParser<HtmlPayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const buf = await res.arrayBuffer();
  const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
  return { type: "html", html: value };
};

export const parserRegistry: Partial<Record<PreviewKind, PreviewParser<PreviewPayload>>> = {
  md: async (r) => parseText(r),
  text: async (r) => {
    // Best-effort size guard for large text-based structured files.
    const ext = extFromPath(r.path);
    if (ext === "json" || ext === "csv") {
      const guarded = await fetchTextWithSizeGuard(r);
      if (guarded.tooLarge) return { type: "text", text: guarded.text || `（${guarded.warning ?? "文件过大"}）` };
      // reuse the normal parser by forcing the same input text path; keep it simple:
      // call parseText which will fetch again would be wasteful; so inline the small branch.
      const text = guarded.text;
      if (ext === "csv") {
        const { header, body, isTruncated, totalRows, totalColumns } = parseCsvBasic(text);
        const columns = buildColumnsFromHeader(header);
        const bodyCut = body.map((rr) => hardCutColumns(rr));
        const rows = rowsToRecords(columns, bodyCut);
        return {
          type: "datagrid",
          sourceText: text,
          columns,
          rows,
          isTruncated: isTruncated || (totalColumns ?? 0) > MAX_GRID_COLS,
          totalRows,
          totalColumns,
          warning:
            isTruncated || (totalColumns ?? 0) > MAX_GRID_COLS
              ? `⚠️ 预览已截断：当前文件过大，仅展示前 ${MAX_GRID_ROWS} 行 / ${MAX_GRID_COLS} 列。请下载原文件查看完整数据。`
              : undefined,
        };
      }
      try {
        const parsed = JSON.parse(text) as unknown;
        const grid = jsonToGrid(parsed);
        return {
          type: "datagrid",
          sourceText: text,
          columns: grid.columns,
          rows: grid.rows,
          isTruncated: grid.isTruncated || (grid.totalColumns ?? 0) > MAX_GRID_COLS,
          totalRows: grid.totalRows,
          totalColumns: grid.totalColumns,
          warning:
            grid.isTruncated
              ? `⚠️ 预览已截断：当前文件过大，仅展示前 ${MAX_GRID_ROWS} 行。请下载原文件查看完整数据。`
              : undefined,
        };
      } catch {
        return { type: "text", text };
      }
    }
    return parseText(r);
  },
  mermaid: async (r) => parseMermaid(r),
  xlsx: async (r) => parseXlsx(r),
  docx: async (r) => parseDocx(r),
};

export const defaultParser: PreviewParser<PreviewPayload> = async () => ({ type: "none" });

/**
 * Mermaid 渲染需要 id；为了保持纯粹且可复现，用 path 派生一个稳定 id。
 * 不依赖 useId / 随机数，避免重复渲染时 DOM 混乱。
 */
function stableMermaidId(path: string): string {
  let h = 0;
  for (let i = 0; i < path.length; i++) h = (h * 31 + path.charCodeAt(i)) >>> 0;
  return String(h);
}

