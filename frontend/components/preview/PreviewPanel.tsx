"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { FileSearch, Loader2, X as XIcon } from "lucide-react";
import * as XLSX from "xlsx";
import mammoth from "mammoth/mammoth.browser.js";
import mermaid from "mermaid";
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
import type { PreviewResolution } from "./previewTypes";

export type PreviewTabItem = { id: string; path: string; label: string };

type Props = {
  onClose: () => void;
  /** 预览类 Tab（文件 / browser），与中栏模块大盘互不抢焦点 */
  previewTabs: PreviewTabItem[];
  activeTabId: string | null;
  onSelectTab: (id: string) => void;
  onClosePreviewTab: (id: string) => void;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
};

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "embed"; kind: "image" | "pdf" | "html"; url: string }
  | { status: "text"; text: string; markdown: boolean; lang?: string }
  | { status: "html"; html: string }
  | { status: "table"; rows: string[][] }
  | { status: "mermaid"; svg: string; source: string }
  | { status: "binary"; url: string; name: string };

// Map file extensions to Prism language names
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

// ─── FilePreviewBody ─────────────────────────────────────────────────────────

function FilePreviewBody({
  path,
  onOpenPath,
  activeSkillName,
  onFillInput,
  onClosePanel,
}: {
  path: string;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
  onClosePanel?: () => void;
}) {
  const [state, setState] = useState<PreviewState>({ status: "loading" });
  const resolution: PreviewResolution = useMemo(() => resolvePreview(path), [path]);
  const url = resolution.url;
  const kind: PreviewKind = resolution.kind;
  const mermaidId = useId().replace(/:/g, "");

  useEffect(() => {
    // browser / skill-ui：由 renderer 直接渲染，无需预取
    if (resolution.fetch === "none") {
      if (kind === "binary" && url) {
        const name = path.split(/[/\\]/).pop() ?? "file";
        setState({ status: "binary", url, name });
      } else if ((kind === "image" || kind === "pdf" || kind === "html") && url) {
        setState({ status: "embed", kind, url });
      } else {
        // browser / skill-ui
        setState({ status: "idle" });
      }
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });

    (async () => {
      try {
        if (!url) throw new Error("missing preview url");
        const res = await fetch(url);
        if (!res.ok) {
          const t = await res.text().catch(() => "");
          throw new Error(t || `HTTP ${res.status}`);
        }

        if (resolution.fetch === "text") {
          const text = await res.text();
          if (cancelled) return;
          if (kind === "mermaid") {
            mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
            const { svg } = await mermaid.render(`mmd-${mermaidId}`, text);
            if (!cancelled) setState({ status: "mermaid", svg, source: text });
            return;
          }
          if (kind === "md") {
            setState({ status: "text", text, markdown: true });
            return;
          }
          const lang = getLangFromPath(path);
          setState({ status: "text", text, markdown: false, lang });
          return;
        }

        if (resolution.fetch === "arrayBuffer" && kind === "xlsx") {
          const buf = await res.arrayBuffer();
          if (cancelled) return;
          const wb = XLSX.read(buf, { type: "array" });
          const sheetName = wb.SheetNames[0];
          if (!sheetName) throw new Error("empty workbook");
          const sheet = wb.Sheets[sheetName];
          const rows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, defval: "" }) as string[][];
          setState({ status: "table", rows });
          return;
        }

        if (resolution.fetch === "arrayBuffer" && kind === "docx") {
          const buf = await res.arrayBuffer();
          if (cancelled) return;
          const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
          setState({ status: "html", html: value });
        }
      } catch (e) {
        if (!cancelled)
          setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
      }
    })();

    return () => { cancelled = true; };
  }, [path, url, kind, mermaidId, resolution.fetch]);

  if (kind === "browser") {
    return <BrowserRenderer path={path} resolution={resolution} onClosePanel={onClosePanel} />;
  }

  if (kind === "skill-ui") {
    return <SkillUiNoticeRenderer />;
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
      <div className="rounded-xl text-sm p-3 whitespace-pre-wrap"
        style={{ border: "1px solid rgba(239,107,115,0.24)", background: "rgba(239,107,115,0.08)", color: "var(--danger)" }}>
        {state.message}
      </div>
    );
  }

  if (state.status === "embed") {
    return <EmbedRenderer path={path} resolution={resolution} url={state.url} embedKind={state.kind} />;
  }

  if (state.status === "text" && state.markdown) {
    return (
      <MarkdownRenderer
        path={path}
        resolution={resolution}
        text={state.text}
        onOpenPath={onOpenPath}
        activeSkillName={activeSkillName}
        onFillInput={onFillInput}
      />
    );
  }

  if (state.status === "text") {
    return <CodeRenderer path={path} resolution={resolution} code={state.text} lang={state.lang} />;
  }

  if (state.status === "html") {
    return <HtmlRenderer path={path} resolution={resolution} html={state.html} />;
  }

  if (state.status === "table") {
    return <TableRenderer path={path} resolution={resolution} rows={state.rows} />;
  }

  if (state.status === "mermaid") {
    return <MermaidRenderer path={path} resolution={resolution} svg={state.svg} source={state.source} />;
  }

  if (state.status === "binary") {
    return <BinaryRenderer path={path} resolution={resolution} url={state.url} name={state.name} />;
  }

  return null;
}

// ─── PreviewPanel (exported) ─────────────────────────────────────────────────

export function PreviewPanel({
  onClose,
  previewTabs,
  activeTabId,
  onSelectTab,
  onClosePreviewTab,
  onOpenPath,
  activeSkillName,
  onFillInput,
}: Props) {
  const tabs = useMemo(() => {
    const out: Array<{ id: string; label: string; path: string; kind: "preview" }> = [];
    for (const t of previewTabs) out.push({ id: t.id, label: t.label, path: t.path, kind: "preview" });
    return out;
  }, [previewTabs]);

  const effectiveActiveTabId = useMemo(() => {
    if (activeTabId && tabs.some((t) => t.id === activeTabId)) return activeTabId;
    return previewTabs[0]?.id ?? null;
  }, [activeTabId, previewTabs, tabs]);

  const activeTab = useMemo(
    () => (effectiveActiveTabId ? tabs.find((t) => t.id === effectiveActiveTabId) ?? null : null),
    [tabs, effectiveActiveTabId],
  );

  const showPathRow = false;

  return (
    <aside className="h-full min-h-0 flex flex-col gap-3 p-0 bg-transparent border-0 shadow-none text-[var(--text-primary)]">
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
          <XIcon size={14} />
        </button>
      </div>

      {showPathRow && null}

      <div className="flex flex-col flex-1 min-h-0 overflow-hidden rounded-2xl bg-[var(--paper-card)] border border-[var(--border-subtle)] text-[var(--text-primary)] shadow-[var(--shadow-panel)]">
        <div
          className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-[var(--border-subtle)] dark:border-white/10 bg-[var(--surface-3)]/80 dark:bg-black/25 px-1 py-1"
          role="tablist"
          aria-label="右侧面板标签"
        >
          {tabs.map((tab) => {
            const selected = tab.id === effectiveActiveTabId;
            const closable = tab.kind === "preview";
            return (
              <div
                key={tab.id}
                className={`group flex max-w-[12rem] shrink-0 items-center rounded-md border text-left text-[11px] transition-colors ${
                  selected
                    ? "border-[var(--accent)] bg-[var(--surface-2)] text-[var(--text-primary)]"
                    : "border-transparent bg-transparent ui-text-secondary hover:bg-[var(--surface-2)]"
                }`}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  className="min-w-0 flex-1 truncate px-2 py-1 text-left"
                  title={tab.path}
                  onClick={() => onSelectTab(tab.id)}
                >
                  {tab.label}
                </button>
                {closable && (
                  <button
                    type="button"
                    className="shrink-0 rounded p-1 ui-text-muted opacity-70 hover:opacity-100 hover:bg-[var(--surface-3)]"
                    aria-label={`关闭 ${tab.label}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onClosePreviewTab(tab.id);
                    }}
                  >
                    <XIcon size={12} />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex-1 min-h-0 overflow-auto p-5 bg-[var(--paper-card)]">
          {activeTab?.kind === "preview" && activeTab.path ? (
            <FilePreviewBody
              key={activeTab.path}
              path={activeTab.path}
              onOpenPath={onOpenPath}
              activeSkillName={activeSkillName}
              onFillInput={onFillInput}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="flex w-full max-w-md flex-col items-center justify-center rounded-2xl border-2 border-dashed border-white/10 bg-[color-mix(in_srgb,var(--surface-1)_85%,transparent)] px-8 py-10 text-center">
                <div className="mb-4 rounded-2xl bg-[color-mix(in_srgb,var(--surface-3)_72%,transparent)] p-4 text-[var(--accent)]">
                  <FileSearch size={30} strokeWidth={1.8} className="opacity-85" />
                </div>
                <p className="text-base font-semibold ui-text-primary">暂无预览内容</p>
                <p className="mt-2 text-sm leading-6 ui-text-muted">
                  请在左侧会话中生成产物，或点击文件胶囊按钮在右侧分栏中预览。
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

