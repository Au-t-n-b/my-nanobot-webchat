"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, Copy, FileQuestion, FileSearch, Loader2, Play, Sparkles, X as XIcon } from "lucide-react";
import * as XLSX from "xlsx";
import mammoth from "mammoth/mammoth.browser.js";
import mermaid from "mermaid";
import { ensurePrismLanguagesRegistered, PRISM_LANGUAGE_IDS, SyntaxHighlighter } from "@/lib/prismSyntaxHighlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import { RemoteBrowser } from "@/components/RemoteBrowser";
import { buildProxiedFileUrl } from "@/lib/apiFile";
import { previewKindFromPath, type PreviewKind } from "@/lib/previewKind";

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

// ─── Gantt hover tooltip ────────────────────────────────────────────────────

type TooltipState = {
  visible: boolean;
  x: number;
  y: number;
  label: string;
  detail: string;
};

function GanttView({ svg, source }: { svg: string; source: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0, label: "", detail: "",
  });
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [copied, setCopied] = useState(false);

  const copySource = () => {
    void navigator.clipboard.writeText(source).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Mermaid task rects have class names like "task task0 taskType0" etc.
    const taskEls = container.querySelectorAll<SVGElement>(
      "rect[class*='task'], .task"
    );

    let debounce: ReturnType<typeof setTimeout> | null = null;

    const onEnter = (e: Event) => {
      const ev = e as MouseEvent;
      const el = ev.target as SVGElement;

      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(() => {
        // Try to find label: look for sibling <text> or <title> near the rect
        let label = "";
        let detail = "";

        // Check <title> child
        const title = el.querySelector("title");
        if (title) label = title.textContent ?? "";

        // If no title, walk up to parent g and find text elements
        if (!label) {
          const parentG = el.closest("g");
          if (parentG) {
            const texts = parentG.querySelectorAll("text");
            texts.forEach((t) => {
              const txt = t.textContent?.trim() ?? "";
              if (txt && !label) label = txt;
              else if (txt && txt !== label) detail = txt;
            });
          }
        }

        // Fallback: try class attribute for task id
        if (!label) {
          const cls = el.getAttribute("class") ?? "";
          const match = cls.match(/task\d+/);
          if (match) label = match[0];
        }

        if (!label) label = "任务";

        setTooltip({ visible: true, x: ev.clientX, y: ev.clientY, label, detail });
      }, 80);
    };

    const onLeave = () => {
      if (debounce) clearTimeout(debounce);
      if (hideTimer.current) clearTimeout(hideTimer.current);
      hideTimer.current = setTimeout(() => setTooltip((t) => ({ ...t, visible: false })), 100);
    };

    const onMove = (e: Event) => {
      const ev = e as MouseEvent;
      setTooltip((t) => (t.visible ? { ...t, x: ev.clientX, y: ev.clientY } : t));
    };

    taskEls.forEach((el) => {
      el.addEventListener("mouseenter", onEnter);
      el.addEventListener("mouseleave", onLeave);
      el.addEventListener("mousemove", onMove);
    });

    return () => {
      if (debounce) clearTimeout(debounce);
      taskEls.forEach((el) => {
        el.removeEventListener("mouseenter", onEnter);
        el.removeEventListener("mouseleave", onLeave);
        el.removeEventListener("mousemove", onMove);
      });
    };
  }, [svg]);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-end mb-1">
        <button
          type="button"
          onClick={copySource}
          aria-label="复制源码"
          className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
        >
          {copied ? <Check size={10} /> : <Copy size={10} />}
          {copied ? "已复制" : "复制源码"}
        </button>
      </div>

      <div
        ref={containerRef}
        className="overflow-auto p-2 [&_svg]:max-w-full [&_svg]:h-auto [&_.task]:cursor-pointer [&_.task]:transition-opacity [&_.task:hover]:opacity-80"
        dangerouslySetInnerHTML={{ __html: svg }}
      />

      {/* Tooltip portal-like element */}
      {tooltip.visible && (
        <div
          className="fixed z-50 pointer-events-none"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          <div className="rounded-lg border border-white/10 bg-zinc-800/90 backdrop-blur-md p-3 shadow-xl text-xs text-white max-w-[200px]">
            <p className="font-semibold leading-snug">{tooltip.label}</p>
            {tooltip.detail && (
              <p className="mt-1 text-zinc-400 leading-snug">{tooltip.detail}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Code Block with syntax highlighting ────────────────────────────────────

function CodePreview({ code, lang, filePath }: { code: string; lang?: string; filePath: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const effectiveLang = lang ?? "text";
  const isPlainText = !lang;
  ensurePrismLanguagesRegistered();
  const usePrism =
    Boolean(lang) &&
    lang !== "text" &&
    PRISM_LANGUAGE_IDS.has(effectiveLang);

  return (
    <div className="relative group rounded-xl overflow-hidden border border-[var(--border-subtle)]">
      {/* Floating toolbar */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        <button
          type="button"
          onClick={copy}
          aria-label="复制代码"
          title="一键复制"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-white/80 hover:text-white bg-zinc-700/80 hover:bg-zinc-600/90 backdrop-blur-sm transition-colors"
        >
          {copied ? <Check size={10} className="text-green-400" /> : <Copy size={10} />}
          {copied ? "已复制" : "复制"}
        </button>
        <button
          type="button"
          aria-label="运行（暂未实现）"
          title="运行（暂未实现）"
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-white/50 bg-zinc-700/60 backdrop-blur-sm cursor-not-allowed"
          disabled
        >
          <Play size={10} />
          运行
        </button>
      </div>

      {/* File path label */}
      <div className="px-3 py-1.5 text-[10px] font-mono ui-text-muted border-b border-[var(--border-subtle)]"
        style={{ background: "var(--surface-3)" }}>
        {filePath.replace(/\\/g, "/").split("/").pop()}
        {effectiveLang !== "text" && (
          <span className="ml-2 rounded px-1.5 py-0.5 text-[9px]"
            style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
            {effectiveLang}
          </span>
        )}
      </div>

      {isPlainText || !usePrism ? (
        <pre className="text-xs ui-text-secondary whitespace-pre-wrap font-mono p-3 leading-relaxed overflow-x-auto"
          style={{ background: "var(--surface-2)" }}>
          {code}
        </pre>
      ) : (
        <div className="[&_pre]:!m-0 [&_pre]:!rounded-none [&_pre]:!text-xs [&_.linenumber]:!text-zinc-500 [&_.linenumber]:!min-w-[2.5em] overflow-x-auto">
          <SyntaxHighlighter
            language={effectiveLang}
            style={vscDarkPlus}
            showLineNumbers
            lineNumberStyle={{ color: "#4b5563", minWidth: "2.5em" }}
            customStyle={{ margin: 0, borderRadius: 0, fontSize: "0.75rem", background: "#1e1e2e" }}
            wrapLongLines={false}
          >
            {code}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  );
}

// ─── Quick Try section (for skill files) ────────────────────────────────────

function QuickTrySection({
  skillName,
  onFillInput,
}: {
  skillName: string;
  onFillInput: (text: string) => void;
}) {
  const prompts = [
    `请使用 ${skillName} 技能帮我完成一个任务`,
    `演示 ${skillName} 的使用方式和最佳实践`,
  ];

  return (
    <div className="mt-6 pt-4 border-t border-[var(--border-subtle)]">
      <p className="text-xs font-semibold ui-text-secondary mb-3 flex items-center gap-1.5">
        <Sparkles size={12} style={{ color: "var(--warning)" }} />
        💡 快速尝试 <span className="font-normal ui-text-muted">Quick Try</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onFillInput(prompt)}
            className="rounded-full px-3 py-1.5 text-xs border transition-colors"
            style={{
              borderColor: "rgba(245,158,11,0.3)",
              color: "rgb(245,158,11)",
              background: "transparent",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = "rgba(245,158,11,0.1)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = "transparent";
            }}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── CopySourceBar (unchanged helper) ──────────────────────────────────────

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
  const url = useMemo(() => buildProxiedFileUrl(path), [path]);
  const kind: PreviewKind = useMemo(() => previewKindFromPath(path), [path]);
  const mermaidId = useId().replace(/:/g, "");

  useEffect(() => {
    // Remote browser / Skill UI: dedicated render below; skip file fetch.
    if (kind === "browser") return;
    if (kind === "skill-ui") return;

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

        if (kind === "xlsx") {
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

        if (kind === "docx") {
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
  }, [path, url, kind, mermaidId]);

  const isSkillFile =
    activeSkillName != null &&
    (path.toLowerCase().includes("/skills/") || path.toLowerCase().replace(/\\/g, "/").includes("\\skills\\")) &&
    path.toLowerCase().endsWith(".md");

  // Remote browser – render after all hooks, before file-fetch status checks
  if (kind === "browser") {
    return <RemoteBrowser filePath={path} onClosePanel={onClosePanel} />;
  }

  if (kind === "skill-ui") {
    return (
      <div
        className="rounded-xl p-4 text-sm ui-text-secondary"
        style={{
          border: "1px solid rgba(245,158,11,0.30)",
          background: "rgba(245,158,11,0.06)",
        }}
      >
        右侧预览栏仅用于产物参考（文件 / 网页 / 表格）。模块大盘（SDUI）请在中栏打开。
      </div>
    );
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
    if (state.kind === "image") return <ImageEmbed url={state.url} path={path} />;
    return (
      <div className="rounded-xl border border-black/[0.06] dark:border-white/10 bg-slate-100/90 dark:bg-black/40 p-2 shadow-inner overflow-hidden">
        <iframe
          title="preview"
          src={state.url}
          className="w-full min-h-[500px] rounded-lg border border-black/[0.08] dark:border-white/10 bg-white"
        />
      </div>
    );
  }

  if (state.status === "text" && state.markdown) {
    return (
      <div className="max-w-none text-sm">
        <CopySourceBar text={state.text} />
        <AgentMarkdown content={state.text} onFileLinkClick={onOpenPath} />
        {isSkillFile && onFillInput && activeSkillName && (
          <QuickTrySection skillName={activeSkillName} onFillInput={onFillInput} />
        )}
      </div>
    );
  }

  if (state.status === "text") {
    return (
      <CodePreview
        code={state.text}
        lang={state.lang}
        filePath={path}
      />
    );
  }

  if (state.status === "html") {
    return (
      <div
        className="max-w-none text-sm ui-text-primary p-3 rounded-xl border border-[var(--border-subtle)] dark:border-white/10 bg-[var(--surface-2)] dark:bg-black/35 dark:shadow-inner [&_a]:ui-link [&_p]:mb-2"
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
    return <GanttView svg={state.svg} source={state.source} />;
  }

  if (state.status === "binary") {
    return (
      <div className="text-sm ui-text-secondary flex flex-col gap-3 items-start">
        <FileQuestion size={32} className="ui-text-muted" />
        <p>无法内联预览此类型，可通过下方链接下载。</p>
        <a href={state.url} download={state.name} className="ui-btn-accent rounded-md px-3 py-1.5">
          打开 / 下载 {state.name}
        </a>
      </div>
    );
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
