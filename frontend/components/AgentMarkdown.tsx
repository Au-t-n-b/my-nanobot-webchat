"use client";

import { isValidElement, useState, type ReactElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
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
const WIN_PATH_RE = new RegExp(
  "(?<![`\\[(\\[])([A-Za-z]:[/\\\\][^\\s`\\]\\)\"'\\n]{3,}\\.(?:" + FILE_EXT_RE + "))",
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

const FOLD_THRESHOLD = 15;

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
  const lines = code.split("\n").filter((l, i, arr) => !(i === arr.length - 1 && l === "")).length;
  const shouldFold = lines > FOLD_THRESHOLD;
  const [collapsed, setCollapsed] = useState(shouldFold);
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

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
      const path = extractLocalPreviewPath(href ?? undefined);
      if (path) {
        const displayHref = buildProxiedFileUrl(path);
        const label = fileBasename(path);
        const inline = isInlineExt(path);

        if (inline && onToggleInline) {
          // Render InlinePreviewBlock OUTSIDE the <p> (in AgentMarkdown wrapper),
          // only toggle state here to avoid <div> inside <p> hydration error.
          return (
            <a
              {...rest}
              href={displayHref}
              title={path}
              className="ui-link underline decoration-dotted"
              onClick={(e) => { e.preventDefault(); onToggleInline(path); }}
            >
              {label}
            </a>
          );
        }

        if (onFileLinkClick) {
          return (
            <a
              {...rest}
              href={displayHref}
              title={path}
              className="ui-link underline decoration-dotted"
              onClick={(e) => { e.preventDefault(); onFileLinkClick(path); }}
            >
              {label}
            </a>
          );
        }
      }
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
      <p className="mb-2 last:mb-0">
        {typeof children === "string" ? highlight(children) : children}
      </p>
    ),
    ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
    li: ({ children }) => <li>{children}</li>,
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
