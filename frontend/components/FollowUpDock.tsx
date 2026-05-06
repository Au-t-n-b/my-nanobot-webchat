"use client";

import { ArrowRight, Sparkles } from "lucide-react";

type FollowUp = { id: string; label: string; prompt: string };

const DEFAULT_FOLLOWUPS: FollowUp[] = [
  { id: "continue", label: "继续", prompt: "请继续。" },
  { id: "summarize", label: "总结要点", prompt: "请把上面的内容用 5 条要点精炼总结。" },
  { id: "next", label: "下一步建议", prompt: "基于上面的输出，给我 3 个具体可行的下一步建议。" },
];

type Props = {
  onPick: (text: string) => void;
  followups?: FollowUp[];
};

export function FollowUpDock({ onPick, followups = DEFAULT_FOLLOWUPS }: Props) {
  return (
    <div className="mx-auto flex w-full max-w-3xl xl:max-w-[56rem] 2xl:max-w-[64rem] flex-wrap items-center gap-2.5 pb-2">
      <span
        className="text-[11px] font-bold tracking-[0.12em] inline-flex items-center gap-1.5"
        style={{ color: "var(--accent)" }}
      >
        <Sparkles size={14} strokeWidth={2.5} aria-hidden />
        FOLLOW-UP
      </span>
      {followups.map((f) => (
        <button
          key={f.id}
          type="button"
          onClick={() => onPick(f.prompt)}
          className="ui-followup-chip group"
          title={f.prompt}
        >
          <span>{f.label}</span>
          <ArrowRight
            size={13}
            strokeWidth={2.25}
            aria-hidden
            className="ui-motion-fast opacity-50 -translate-x-0.5 group-hover:opacity-100 group-hover:translate-x-0"
          />
        </button>
      ))}
    </div>
  );
}
