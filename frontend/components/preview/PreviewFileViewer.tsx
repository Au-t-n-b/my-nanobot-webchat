"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import type { PreviewKind } from "@/lib/previewKind";
import { resolvePreview } from "./previewResolver";
import { BrowserRenderer } from "./renderers/BrowserRenderer";
import { SkillUiNoticeRenderer } from "./renderers/SkillUiNoticeRenderer";
import { EmbedRenderer } from "./renderers/EmbedRenderer";
import { MarkdownRenderer } from "./renderers/MarkdownRenderer";
import { CodeRenderer } from "./renderers/CodeRenderer";
import { HtmlRenderer } from "./renderers/HtmlRenderer";
import { TableRenderer } from "./renderers/TableRenderer";
import { MermaidRenderer } from "./renderers/MermaidRenderer";
import { BinaryRenderer } from "./renderers/BinaryRenderer";
import { DataGridRenderer } from "./renderers/DataGridRenderer";
import { XlsxRenderer } from "./renderers/XlsxRenderer";
import { ArchiveRenderer } from "./renderers/ArchiveRenderer";
import { defaultParser, parserRegistry, type PreviewPayload } from "./previewParsers";
import type { PreviewResolution } from "./previewTypes";

export type PreviewFileViewerProps = {
  path: string;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
  initialBuffer?: ArrayBuffer;
  onClosePanel?: () => void;
};

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string };

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript", tsx: "typescript",
  js: "javascript", jsx: "javascript",
  py: "python",
  json: "json",
  yaml: "yaml", yml: "yaml", toml: "toml",
  sh: "bash", bash: "bash",
  css: "css",
  rs: "rust",
  xml: "markup", html: "markup", htm: "markup",
};

function getLangFromPath(p: string): string | undefined {
  const ext = p.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TO_LANG[ext];
}

export function PreviewFileViewer({
  path,
  onOpenPath,
  activeSkillName,
  onFillInput,
  initialBuffer,
  onClosePanel,
}: PreviewFileViewerProps) {
  const [state, setState] = useState<PreviewState>({ status: "loading" });
  const resolution: PreviewResolution = useMemo(() => resolvePreview(path), [path]);
  const kind: PreviewKind = resolution.kind;
  const [payload, setPayload] = useState<PreviewPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    setPayload(null);

    (async () => {
      try {
        if (resolution.fetch === "none") {
          if (!cancelled) setState({ status: "idle" });
          return;
        }
        const parser = parserRegistry[resolution.kind] ?? defaultParser;
        const data = await parser(resolution, { initialBuffer });
        if (cancelled) return;
        setPayload(data);
        setState({ status: "idle" });
      } catch (e) {
        if (!cancelled) {
          setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
        }
      }
    })();

    return () => { cancelled = true; };
  }, [resolution, initialBuffer]);

  if (kind === "browser") {
    return <BrowserRenderer path={path} resolution={resolution} onClosePanel={onClosePanel} />;
  }

  if (kind === "skill-ui") {
    return <SkillUiNoticeRenderer />;
  }

  if (resolution.fetch === "none") {
    const url = resolution.url;
    if (kind === "binary" && url) {
      const name = path.split(/[/\\]/).pop() ?? "file";
      return <BinaryRenderer path={path} resolution={resolution} url={url} name={name} />;
    }
    if ((kind === "image" || kind === "pdf" || kind === "html") && url) {
      return <EmbedRenderer path={path} resolution={resolution} url={url} embedKind={kind} />;
    }
  }

  if (state.status === "loading") {
    return (
      <div className="flex items-center justify-center gap-2 text-zinc-400 text-sm py-8">
        <Loader2 className="animate-spin" size={18} />
        <span className="ui-text-muted">加载中…</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div
        className="rounded-xl text-sm p-3 whitespace-pre-wrap"
        style={{ border: "1px solid rgba(239,107,115,0.24)", background: "rgba(239,107,115,0.08)", color: "var(--danger)" }}
      >
        {state.message}
      </div>
    );
  }

  if (!payload) return null;

  if (payload.type === "markdown") {
    return (
      <MarkdownRenderer
        path={path}
        resolution={resolution}
        text={payload.text}
        onOpenPath={onOpenPath}
        activeSkillName={activeSkillName}
        onFillInput={onFillInput}
      />
    );
  }

  if (payload.type === "text") {
    const lang = getLangFromPath(path);
    return <CodeRenderer path={path} resolution={resolution} code={payload.text} lang={lang} />;
  }

  if (payload.type === "datagrid") {
    const lang = getLangFromPath(path);
    const SourceRenderer = ({ text }: { text: string }) => (
      <CodeRenderer path={path} resolution={resolution} code={text} lang={lang ?? "json"} />
    );
    return (
      <DataGridRenderer
        path={path}
        resolution={resolution}
        payload={{
          sourceText: payload.sourceText,
          columns: payload.columns,
          rows: payload.rows,
          isTruncated: payload.isTruncated,
          warning: payload.warning,
        }}
        SourceRenderer={SourceRenderer}
      />
    );
  }

  if (payload.type === "html") {
    return <HtmlRenderer path={path} resolution={resolution} html={payload.html} />;
  }

  if (payload.type === "table") {
    return <TableRenderer path={path} resolution={resolution} rows={payload.rows} />;
  }

  if (payload.type === "xlsx") {
    return (
      <XlsxRenderer
        path={path}
        resolution={resolution}
        payload={{
          sheets: payload.sheets.map((s) => ({
            name: s.name,
            rows: s.rows,
            isTruncated: s.isTruncated,
            totalRows: s.totalRows,
            totalColumns: s.totalColumns,
            warning: s.isTruncated
              ? `⚠️ 预览已截断：当前文件过大，仅展示前 1000 行 / 50 列。请下载原文件查看完整数据。`
              : undefined,
          })),
        }}
      />
    );
  }

  if (payload.type === "mermaid") {
    return <MermaidRenderer path={path} resolution={resolution} svg={payload.svg} source={payload.source} />;
  }

  if (payload.type === "zip") {
    return (
      <ArchiveRenderer
        path={path}
        resolution={resolution}
        payload={payload}
        onOpenPath={onOpenPath}
        activeSkillName={activeSkillName}
        onFillInput={onFillInput}
      />
    );
  }

  return null;
}

