"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Check, Copy, FileQuestion, FolderOpen, Loader2, X } from "lucide-react";
import * as XLSX from "xlsx";
import mammoth from "mammoth/mammoth.browser.js";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { buildProxiedFileUrl, openLocation } from "@/lib/apiFile";
import { previewKindFromPath, type PreviewKind } from "@/lib/previewKind";

type Props = {
  onClose: () => void;
  filePath: string | null;
  onClearFile: () => void;
  onOpenPath: (path: string) => void;
};

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "embed"; kind: "image" | "pdf" | "html"; url: string }
  | { status: "text"; text: string; markdown: boolean }
  | { status: "html"; html: string }
  | { status: "table"; rows: string[][] }
  | { status: "mermaid"; svg: string; source: string }
  | { status: "binary"; url: string; name: string };

function displayPreviewPath(fullPath: string): string {
  const normalized = fullPath.replace(/\\/g, "/");
  const marker = "/.nanobot/workspace/";
  const idx = normalized.toLowerCase().indexOf(marker);
  if (idx >= 0) return `./workspace/${normalized.slice(idx + marker.length)}`;
  return normalized;
}

function CopySourceBar({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex justify-end mb-1">
      <button
        type="button"
        onClick={copy}
        aria-label="复制源码"
        className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
      >
        {copied ? <Check size={10} /> : <Copy size={10} />}
        {copied ? "已复制" : "复制源码"}
      </button>
    </div>
  );
}

function ImageEmbed({ url, path }: { url: string; path: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(path).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex flex-col items-center gap-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="" className="max-w-full object-contain mx-auto" />
      <button
        type="button"
        onClick={copy}
        aria-label="复制文件路径"
        className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-xs ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
      >
        {copied ? <Check size={10} /> : <Copy size={10} />}
        {copied ? "已复制路径" : "复制路径"}
      </button>
    </div>
  );
}

function FilePreviewBody({
  path,
  onOpenPath,
}: {
  path: string;
  onOpenPath: (path: string) => void;
}) {
  const [state, setState] = useState<PreviewState>({ status: "loading" });
  const url = useMemo(() => buildProxiedFileUrl(path), [path]);
  const kind: PreviewKind = useMemo(() => previewKindFromPath(path), [path]);
  const mermaidId = useId().replace(/:/g, "");

  useEffect(() => {
    if (kind === "binary") {
      const name = path.split(/[/\\]/).pop() ?? "file";
      setState({ status: "binary", url, name });
      return;
    }

    if (kind === "image" || kind === "pdf" || kind === "html") {
      setState({ status: "embed", kind, url });
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });

    (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) {
          const t = await res.text().catch(() => "");
          throw new Error(t || `HTTP ${res.status}`);
        }

        if (kind === "md" || kind === "text" || kind === "mermaid") {
          const text = await res.text();
          if (cancelled) return;
          if (kind === "mermaid") {
            const m = await import("mermaid");
            m.default.initialize({
              startOnLoad: false,
              theme: "dark",
              securityLevel: "strict",
            });
            const { svg } = await m.default.render(`mmd-${mermaidId}`, text);
            if (!cancelled) setState({ status: "mermaid", svg, source: text });
            return;
          }
          if (kind === "md") {
            setState({ status: "text", text, markdown: true });
            return;
          }
          setState({ status: "text", text, markdown: false });
          return;
        }

        if (kind === "xlsx") {
          const buf = await res.arrayBuffer();
          if (cancelled) return;
          const wb = XLSX.read(buf, { type: "array" });
          const sheetName = wb.SheetNames[0];
          if (!sheetName) throw new Error("empty workbook");
          const sheet = wb.Sheets[sheetName];
          const rows = XLSX.utils.sheet_to_json<string[]>(sheet, {
            header: 1,
            defval: "",
          }) as string[][];
          setState({ status: "table", rows });
          return;
        }

        if (kind === "docx") {
          const buf = await res.arrayBuffer();
          if (cancelled) return;
          const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
          setState({ status: "html", html: value });
        }
      } catch (e) {
        if (!cancelled) setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [path, url, kind, mermaidId]);

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
      <div className="rounded-xl text-sm p-3 whitespace-pre-wrap" style={{ border: "1px solid rgba(239,107,115,0.24)", background: "rgba(239,107,115,0.08)", color: "var(--danger)" }}>
        {state.message}
      </div>
    );
  }

  if (state.status === "embed") {
    if (state.kind === "image") {
      return <ImageEmbed url={state.url} path={path} />;
    }
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-3)] p-2 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
        <iframe
          title="preview"
          src={state.url}
          className={
            "w-full min-h-[500px] rounded-lg border border-[var(--border-subtle)] bg-white"
          }
        />
      </div>
    );
  }

  if (state.status === "text" && state.markdown) {
    return (
      <div className="max-w-none text-sm">
        <CopySourceBar text={state.text} />
        <AgentMarkdown content={state.text} onFileLinkClick={onOpenPath} />
      </div>
    );
  }

  if (state.status === "text") {
    return (
      <div className="flex flex-col gap-1">
        <CopySourceBar text={state.text} />
        <pre className="text-xs ui-text-secondary whitespace-pre-wrap font-mono p-2 rounded-xl ui-subtle">
          {state.text}
        </pre>
      </div>
    );
  }

  if (state.status === "html") {
    return (
      <div
        className="max-w-none text-sm ui-text-primary p-2 rounded-xl ui-subtle [&_a]:ui-link [&_p]:mb-2"
        dangerouslySetInnerHTML={{ __html: state.html }}
      />
    );
  }

  if (state.status === "table") {
    return (
      <div className="overflow-auto border border-[var(--border-subtle)] rounded-xl">
        <table className="text-xs ui-text-primary border-collapse w-full">
          <tbody>
            {state.rows.map((row, i) => (
              <tr key={i} className="border-b border-[var(--border-subtle)]">
                {row.map((cell, j) => (
                  <td key={j} className="border-r border-[var(--border-subtle)] px-2 py-1 align-top">
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (state.status === "mermaid") {
    return (
      <div className="flex flex-col gap-1">
        <CopySourceBar text={state.source} />
        <div
          className="overflow-auto p-2 [&_svg]:max-w-full [&_svg]:h-auto"
          dangerouslySetInnerHTML={{ __html: state.svg }}
        />
      </div>
    );
  }

  if (state.status === "binary") {
    return (
      <div className="text-sm ui-text-secondary flex flex-col gap-3 items-start">
        <FileQuestion size={32} className="ui-text-muted" />
        <p>无法内联预览此类型，可通过下方链接下载。</p>
        <a
          href={state.url}
          download={state.name}
          className="ui-btn-accent rounded-md px-3 py-1.5"
        >
          打开 / 下载 {state.name}
        </a>
      </div>
    );
  }

  return null;
}

export function PreviewPanel({ onClose, filePath, onClearFile, onOpenPath }: Props) {
  const [copiedPath, setCopiedPath] = useState(false);
  const copyPath = () => {
    if (!filePath) return;
    void navigator.clipboard.writeText(filePath).then(() => {
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 1200);
    });
  };
  const handleOpenLocation = () => {
    if (!filePath) return;
    void openLocation(filePath);
  };
  return (
    <aside className="ui-panel h-full rounded-2xl p-4 flex flex-col gap-3 min-h-0">
      <div className="flex items-center justify-between gap-2 shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
          预览 <span className="font-normal normal-case tracking-normal ui-text-muted">Preview</span>
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 ui-text-muted hover:text-[var(--text-primary)] hover:bg-[var(--surface-3)] transition-colors"
          aria-label="关闭预览栏"
        >
          <X size={14} />
        </button>
      </div>
      {filePath && (
        <div className="flex items-center gap-1.5 shrink-0 min-w-0">
          <p className="text-xs ui-text-muted truncate min-w-0 flex-1" title={filePath}>
            {displayPreviewPath(filePath)}
          </p>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={copyPath}
              aria-label="复制完整路径"
              title={copiedPath ? "已复制！" : "复制完整路径"}
              className="inline-flex items-center rounded-md border border-[var(--border-subtle)] p-1 ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
            >
              {copiedPath
                ? <Check size={11} style={{ color: "var(--success)" }} />
                : <Copy size={11} />}
            </button>
            <button
              type="button"
              onClick={handleOpenLocation}
              aria-label="在文件管理器中显示"
              title="打开所在位置"
              className="inline-flex items-center rounded-md border border-[var(--border-subtle)] p-1 ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
            >
              <FolderOpen size={11} />
            </button>
          </div>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto rounded-xl p-3 ui-card">
        {filePath ? (
          <FilePreviewBody key={filePath} path={filePath} onOpenPath={onOpenPath} />
        ) : (
          <p className="ui-text-muted text-sm">
            点击对话里的 Markdown 文件链接（例如{" "}
            <code className="ui-text-secondary">[文件名](/api/file?path=相对或绝对路径)</code>
            ），或使用侧栏「高级工具」。请求经本站 <code className="ui-text-secondary">/api/file</code> 代理到
            AGUI，避免浏览器跨域。
          </p>
        )}
      </div>
    </aside>
  );
}
