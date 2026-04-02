"use client";

import { isValidElement, useState, type ReactElement, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, ChevronDown, ChevronUp, Copy } from "lucide-react";
import { buildProxiedFileUrl } from "@/lib/apiFile";
import { InlinePreviewBlock } from "@/components/InlinePreviewBlock";
import { extractLocalPreviewPath } from "@/lib/localFileLink";

// Files that open in the right-side PreviewPanel
const PANEL_EXTS = new Set(["html", "htm", "pdf", "md", "markdown", "docx", "xlsx", "xls",
  "png", "jpg", "jpeg", "gif", "webp", "svg"]);
// Everything else goes inline
function isInlineExt(path: string): boolean {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return ext.length > 0 && !PANEL_EXTS.has(ext);
}

const FILE_EXT_RE =
  "(?:mmd|md|markdown|txt|json|ya?ml|toml|csv|pdf|png|jpe?g|gif|webp|svg|xlsx?|docx|html?|xml|log|ini|ts|tsx|js|jsx|py|rs|sh)";
const BACKTICK_FILE_RE = new RegExp("`([^`\\n]+\\.(?:" + FILE_EXT_RE + "))`", "gi");

// Bare Windows absolute path: C:\... or D:/... (not already in a Markdown link/code)
// (?<![uU]) 避免匹配 skill-ui:// 中的「ui:」后的「i:」（会被误当成盘符 i:）
const WIN_PATH_RE = new RegExp(
  "(?<![`\\[(\\[])(?<![uU])([A-Za-z]:[/\\\\][^\\s`\\]\\)\"'\\n]{3,}\\.(?:" + FILE_EXT_RE + "))",
  "gi",
);
// Bare Unix absolute path starting with /home /Users /tmp /var /opt /workspace
const UNIX_PATH_RE = new RegExp(
  "(?<![`\\[(\\[])(\\/(?:home|Users|tmp|var|opt|workspace)[^\\s`\\]\\)\"'\\n]{3,}\\.(?:" + FILE_EXT_RE + "))",
  "gi",
);

function fileBasename(p: string): string {
  return p.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? p;
}

function normalizeAssistantLinks(content: string): string {
  // 1. backtick filenames → links
  let result = content.replace(BACKTICK_FILE_RE, (_m, p1: string) => {
    const path = String(p1).trim();
    return `[${fileBasename(path)}](${buildProxiedFileUrl(path)})`;
  });
  // 2. bare Windows absolute paths → links
  result = result.replace(WIN_PATH_RE, (_m, p1: string) => {
    const path = String(p1).trim();
    return `[${fileBasename(path)}](${buildProxiedFileUrl(path)})`;
  });
  // 3. bare Unix absolute paths → links
  result = result.replace(UNIX_PATH_RE, (_m, p1: string) => {
    const path = String(p1).trim();
    return `[${fileBasename(path)}](${buildProxiedFileUrl(path)})`;
  });
  return result;
}

const OTHER_CODE_FOLD_THRESHOLD = 12;

function extractCodeText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(extractCodeText).join("");
  if (isValidElement(node)) {
    const el = node as ReactElement<{ children?: ReactNode }>;
    return extractCodeText(el.props.children ?? "");
  }
  return "";
}

function FoldableCodeBlock({ lang, children }: { lang: string; children: React.ReactNode }) {
  const code = extractCodeText(children);
  const normalizedLang = (lang || "").trim().toLowerCase();
  const lines = code.split("\n").filter((l, i, arr) => !(i === arr.length - 1 && l === "")).length;
  const shouldFold =
    normalizedLang === "html" ||
    (lines >= OTHER_CODE_FOLD_THRESHOLD);
  const [collapsed, setCollapsed] = useState(shouldFold);
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const label = normalizedLang === "html" ? "HTML 源码" : (lang ? `${lang} 源码` : "源码");

  if (collapsed && shouldFold) {
    return (
      <div className="my-2 rounded-xl overflow-hidden text-xs ui-card">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="w-full flex items-center justify-between gap-3 px-3 py-2 ui-text-secondary hover:bg-[var(--surface-2)] transition-colors"
          aria-label="展开代码块"
          title="点击展开"
        >
          <span className="truncate">
            [{label} - {lines} lines]
          </span>
          <span className="shrink-0 inline-flex items-center gap-1">
            <span className="text-[10px] ui-text-muted">{copied ? "已复制" : ""}</span>
            <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ui-text-secondary border"
              style={{ borderColor: "var(--border-subtle)", background: "var(--surface-3)" }}
              onClick={(e) => { e.stopPropagation(); copy(); }}
              role="button"
              aria-label="复制代码"
              title="复制"
            >
              {copied ? <Check size={10} /> : <Copy size={10} />}
              复制
            </span>
            <ChevronDown size={12} />
          </span>
        </button>
      </div>
    );
  }

  return (
    <div className="my-2 rounded-xl overflow-hidden text-xs ui-card">
      <div className="flex items-center justify-between px-3 py-1.5 border-b ui-divider" style={{ background: "var(--surface-3)" }}>
        <div className="flex items-center gap-2">
          {lang && (
            <span className="rounded px-1.5 py-0.5 text-[10px] font-mono" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>{lang}</span>
          )}
          <span className="ui-text-muted text-[10px]">{lines} lines</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={copy}
            aria-label="复制代码"
            className="rounded px-1.5 py-0.5 text-[10px] ui-text-secondary hover:bg-[var(--surface-2)] flex items-center gap-1 transition-colors"
          >
            {copied ? <Check size={10} /> : <Copy size={10} />}
            {copied ? "已复制" : "复制"}
          </button>
          {shouldFold && (
            <button
              type="button"
              onClick={() => setCollapsed((v) => !v)}
              aria-label={collapsed ? "展开代码" : "收起代码"}
              className="rounded px-1.5 py-0.5 text-[10px] ui-text-secondary hover:bg-[var(--surface-2)] flex items-center gap-1 transition-colors"
            >
              {collapsed ? <ChevronDown size={10} /> : <ChevronUp size={10} />}
              {collapsed ? "展开" : "收起"}
            </button>
          )}
        </div>
      </div>
      <div
        className={
          collapsed
            ? "max-h-[160px] overflow-hidden transition-[max-height] duration-300"
            : "transition-[max-height] duration-300"
        }
      >
        <pre className="overflow-x-auto p-3 font-mono leading-relaxed">{children}</pre>
      </div>
      {collapsed && (
        <div className="h-6 -mt-6 relative pointer-events-none" style={{ background: "linear-gradient(to top, var(--surface-2), transparent)" }} />
      )}
    </div>
  );
}

export function agentMarkdownComponents(options: {
  onFileLinkClick?: (path: string) => void;
  searchQuery?: string;
  onToggleInline?: (path: string) => void;
}): Components {
  const { onFileLinkClick, searchQuery, onToggleInline } = options;

  function highlight(text: string): React.ReactNode {
    if (!searchQuery?.trim()) return text;
    const escaped = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const parts = text.split(new RegExp(`(${escaped})`, "gi"));
    return parts.map((part, i) =>
      part.toLowerCase() === searchQuery.toLowerCase() ? (
        <mark key={i} className="bg-amber-400/30 rounded text-amber-200">
          {part}
        </mark>
      ) : (
        part
      ),
    );
  }

  return {
    a: ({ href, children, ...rest }) => {
      // External HTTP(S) links: use native <a> WITHOUT preventDefault() to avoid passive event issues
      if (href?.startsWith("http://") || href?.startsWith("https://")) {
        return (
          <a
            {...rest}
            className="ui-link underline"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        );
      }

      // skill-ui:// → Skill UI 右栏（与 RENDER_UI 同源）
      if (href?.startsWith("skill-ui://") && onFileLinkClick) {
        const btnLabel =
          typeof children === "string" ? children : "打开 Skill UI 预览";
        return (
          <button
            type="button"
            className="ui-link underline decoration-dotted bg-transparent border-none cursor-pointer p-0 font-inherit"
            title={href}
            onClick={() => onFileLinkClick(href)}
          >
            {btnLabel}
          </button>
        );
      }

      // browser:// custom protocol → open in right-side PreviewPanel
      if (href?.startsWith("browser://") && onFileLinkClick) {
        // [AUTO_OPEN] marker → render as an inviting CTA button, not a raw link
        const label = typeof children === "string" ? children : "";
        if (label === "AUTO_OPEN") {
          return (
            /* span[block] avoids <div> inside <p> hydration error while giving block layout */
            <span className="block mt-3 mb-1">
              <button
                type="button"
                onClick={() => onFileLinkClick(href)}
                className="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors"
                style={{
                  background: "color-mix(in srgb, var(--accent) 10%, transparent)",
                  color: "var(--accent)",
                  border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "color-mix(in srgb, var(--accent) 18%, transparent)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "color-mix(in srgb, var(--accent) 10%, transparent)")}
              >
                🌐 点击打开网页视窗
              </button>
            </span>
          );
        }
        // Use <button> instead of <a> to avoid passive event listener issues
        const btnLabel = typeof children === "string" ? children : "打开网页";
        return (
          <button
            type="button"
            className="ui-link underline decoration-dotted bg-transparent border-none cursor-pointer p-0 font-inherit"
            onClick={() => onFileLinkClick(href)}
          >
            {btnLabel}
          </button>
        );
      }

      const path = extractLocalPreviewPath(href ?? undefined);
      if (path) {
        const label = fileBasename(path);
        const inline = isInlineExt(path);

        if (inline && onToggleInline) {
          // Use <button> instead of <a> to avoid passive event listener issues
          return (
            <button
              type="button"
              title={path}
              className="ui-link underline decoration-dotted bg-transparent border-none cursor-pointer p-0 font-inherit text-left"
              onClick={() => onToggleInline(path)}
            >
              {label}
            </button>
          );
        }

        if (onFileLinkClick) {
          // Use <button> instead of <a> to avoid passive event listener issues
          return (
            <button
              type="button"
              title={path}
              className="ui-link underline decoration-dotted bg-transparent border-none cursor-pointer p-0 font-inherit text-left"
              onClick={() => onFileLinkClick(path)}
            >
              {label}
            </button>
          );
        }
      }
      // Fallback for other protocols
      return (
        <a
          {...rest}
          className="ui-link underline"
          href={href}
          target="_blank"
          rel="noopener noreferrer"
        >
          {children}
        </a>
      );
    },
    p: ({ children }) => (
      <p className="mb-3 last:mb-0 leading-relaxed">
        {typeof children === "string" ? highlight(children) : children}
      </p>
    ),
    ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-2">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-2">{children}</ol>,
    li: ({ children }) => <li className="my-1">{children}</li>,
    code: ({ className, children, ...props }) => {
      const inline = !className;
      if (inline) {
        return (
          <code className="rounded px-1 py-0.5 text-[0.9em] font-mono" style={{ background: "var(--surface-3)", color: "var(--text-primary)" }} {...props}>
            {children}
          </code>
        );
      }
      return (
        <code className={`${className ?? ""} font-mono`} {...props}>
          {children}
        </code>
      );
    },
    pre: ({ children }) => {
      const codeEl = Array.isArray(children)
        ? children.find((c) => c && typeof c === "object" && "props" in c)
        : children;
      const lang =
        codeEl && typeof codeEl === "object" && "props" in (codeEl as object)
          ? ((codeEl as ReactElement<{ className?: string }>).props.className ?? "").replace("language-", "")
          : "";
      return <FoldableCodeBlock lang={lang}>{children}</FoldableCodeBlock>;
    },
  };
}

export function AgentMarkdown({
  content,
  onFileLinkClick,
  searchQuery,
  className,
}: {
  content: string;
  onFileLinkClick?: (path: string) => void;
  searchQuery?: string;
  className?: string;
}) {
  const [inlineOpen, setInlineOpen] = useState<Set<string>>(new Set());
  const toggleInline = (path: string) => {
    setInlineOpen((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };
  const normalized = normalizeAssistantLinks(content);
  return (
    <div className={className ?? "ui-text-primary leading-relaxed break-words"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={(url) =>
          url.startsWith("browser://") || url.startsWith("skill-ui://")
            ? url
            : defaultUrlTransform(url)
        }
        components={agentMarkdownComponents({ onFileLinkClick, searchQuery, onToggleInline: toggleInline })}
      >
        {normalized}
      </ReactMarkdown>
      {/* InlinePreviewBlocks rendered here (outside <p>) to avoid hydration errors */}
      {Array.from(inlineOpen).map((path) => (
        <InlinePreviewBlock key={path} path={path} onClose={() => toggleInline(path)} />
      ))}
    </div>
  );
}
