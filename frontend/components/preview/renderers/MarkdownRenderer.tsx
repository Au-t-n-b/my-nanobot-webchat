"use client";

import { Check, Copy, Sparkles } from "lucide-react";
import { useState } from "react";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import type { BaseRendererProps } from "../previewTypes";

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

export function MarkdownRenderer(
  props: BaseRendererProps & {
    text: string;
    onOpenPath: (path: string) => void;
    activeSkillName?: string | null;
    onFillInput?: (text: string) => void;
  }
) {
  const isSkillFile =
    props.activeSkillName != null &&
    (props.path.toLowerCase().includes("/skills/") || props.path.toLowerCase().replace(/\\/g, "/").includes("\\skills\\")) &&
    props.path.toLowerCase().endsWith(".md");

  return (
    <div className="max-w-none text-sm">
      <CopySourceBar text={props.text} />
      <AgentMarkdown content={props.text} onFileLinkClick={props.onOpenPath} />
      {isSkillFile && props.onFillInput && props.activeSkillName && (
        <QuickTrySection skillName={props.activeSkillName} onFillInput={props.onFillInput} />
      )}
    </div>
  );
}

