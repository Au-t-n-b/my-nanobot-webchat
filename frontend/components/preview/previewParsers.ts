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

export type PreviewPayload =
  | TextPayload
  | MarkdownPayload
  | HtmlPayload
  | TablePayload
  | MermaidPayload
  | { type: "none" };

async function fetchOk(resolution: PreviewResolution): Promise<Response> {
  if (!resolution.url) throw new Error("missing preview url");
  const res = await fetch(resolution.url);
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(t || `HTTP ${res.status}`);
  }
  return res;
}

const parseText: PreviewParser<TextPayload | MarkdownPayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const text = await res.text();
  if (resolution.kind === "md") return { type: "markdown", text };
  return { type: "text", text };
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

const parseXlsx: PreviewParser<TablePayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const buf = await res.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });
  const sheetName = wb.SheetNames[0];
  if (!sheetName) throw new Error("empty workbook");
  const sheet = wb.Sheets[sheetName];
  const rows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, defval: "" }) as string[][];
  return { type: "table", rows };
};

const parseDocx: PreviewParser<HtmlPayload> = async (resolution) => {
  const res = await fetchOk(resolution);
  const buf = await res.arrayBuffer();
  const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
  return { type: "html", html: value };
};

export const parserRegistry: Partial<Record<PreviewKind, PreviewParser<PreviewPayload>>> = {
  md: async (r) => parseText(r),
  text: async (r) => parseText(r),
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

