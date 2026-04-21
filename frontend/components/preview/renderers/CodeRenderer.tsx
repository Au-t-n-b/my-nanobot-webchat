"use client";

import { Check, Copy, Play } from "lucide-react";
import { useState } from "react";
import { ensurePrismLanguagesRegistered, PRISM_LANGUAGE_IDS, SyntaxHighlighter } from "@/lib/prismSyntaxHighlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { BaseRendererProps } from "../previewTypes";

export function CodeRenderer(
  props: BaseRendererProps & { code: string; lang?: string }
) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(props.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const effectiveLang = props.lang ?? "text";
  const isPlainText = !props.lang;
  ensurePrismLanguagesRegistered();
  const usePrism =
    Boolean(props.lang) &&
    props.lang !== "text" &&
    PRISM_LANGUAGE_IDS.has(effectiveLang);

  return (
    <div className="relative group rounded-xl overflow-hidden border border-[var(--border-subtle)]">
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

      <div
        className="px-3 py-1.5 text-[10px] font-mono ui-text-muted border-b border-[var(--border-subtle)]"
        style={{ background: "var(--surface-3)" }}
      >
        {props.path.replace(/\\/g, "/").split("/").pop()}
        {effectiveLang !== "text" && (
          <span
            className="ml-2 rounded px-1.5 py-0.5 text-[9px]"
            style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
          >
            {effectiveLang}
          </span>
        )}
      </div>

      {isPlainText || !usePrism ? (
        <pre
          className="text-xs ui-text-secondary whitespace-pre-wrap font-mono p-3 leading-relaxed overflow-x-auto"
          style={{ background: "var(--surface-2)" }}
        >
          {props.code}
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
            {props.code}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  );
}

