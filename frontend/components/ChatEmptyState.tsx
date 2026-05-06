"use client";

import { Code2, FileSearch, Lightbulb, Sparkles, type LucideIcon } from "lucide-react";

type QuickStart = {
  id: string;
  cat: string;
  label: string;
  prompt: string;
  icon: LucideIcon;
};

const QUICK_STARTS: QuickStart[] = [
  {
    id: "brainstorm",
    cat: "灵感",
    label: "帮我头脑风暴一个产品方向",
    prompt: "我想做一个面向开发者的工具，帮我头脑风暴 3 个差异化方向，按可行性排序。",
    icon: Lightbulb,
  },
  {
    id: "summarize",
    cat: "总结",
    label: "提炼一份长文档的核心要点",
    prompt: "请把我接下来粘贴的文档总结成 5 条核心要点，并指出可能的风险或盲区。",
    icon: Sparkles,
  },
  {
    id: "research",
    cat: "研究",
    label: "对比两个候选方案的优劣",
    prompt: "对比 A 方案与 B 方案，从可维护性、性能、上手成本三个维度给出结构化建议。",
    icon: FileSearch,
  },
  {
    id: "code",
    cat: "代码",
    label: "解释一段代码的工作原理",
    prompt: "解释下面这段代码做了什么、为什么要这么写，并指出潜在 bug：\n\n```\n\n```",
    icon: Code2,
  },
];

type Props = {
  onPick: (text: string) => void;
};

export function ChatEmptyState({ onPick }: Props) {
  return (
    <div className="flex h-full w-full items-center justify-center px-4 py-8 sm:py-12">
      <div className="flex w-full max-w-2xl flex-col items-center gap-8 text-center">
        <div className="flex flex-col items-center gap-3">
          <span
            aria-hidden
            className="ui-text-eyebrow ui-text-muted inline-flex items-center gap-1.5"
          >
            <span
              className="h-1 w-1 rounded-full"
              style={{ background: "var(--accent)" }}
            />
            NANOBOT · READY
          </span>
          <h1 className="ui-headline-aurora text-3xl font-semibold tracking-tight sm:text-4xl">
            今天，想完成什么？
          </h1>
          <p className="ui-text-secondary mx-auto max-w-md text-sm leading-relaxed">
            选择一个起点，或直接在下方输入。
          </p>
        </div>

        <div className="grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2">
          {QUICK_STARTS.map(({ id, cat, label, prompt, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => onPick(prompt)}
              className="ui-quick-chip group/chip"
            >
              <span
                aria-hidden
                className="ui-quick-chip-icon inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
              >
                <Icon size={16} strokeWidth={1.75} />
              </span>
              <span className="flex flex-1 flex-col items-start min-w-0">
                <span className="ui-text-eyebrow ui-text-muted">{cat}</span>
                <span className="block w-full truncate text-sm font-medium ui-text-primary">
                  {label}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
