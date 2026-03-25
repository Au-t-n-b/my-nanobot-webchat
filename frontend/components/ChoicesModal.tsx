"use client";

import type { ChoiceItem } from "@/hooks/useAgentChat";

type Props = {
  choices: ChoiceItem[] | null;
  onSelect: (choice: ChoiceItem) => void;
  onClose: () => void;
};

export function ChoicesModal({ choices, onSelect, onClose }: Props) {
  if (!choices || choices.length === 0) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="ui-panel w-full max-w-md rounded-2xl p-4">
        <h3 className="text-sm font-semibold ui-text-primary">请选择一个选项</h3>
        <p className="text-xs ui-text-secondary mt-1">选择后会自动作为下一条用户消息发送。</p>
        <div className="mt-4 space-y-2">
          {choices.map((c) => (
            <button
              key={`${c.value}:${c.label}`}
              type="button"
              onClick={() => onSelect(c)}
              className="w-full rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-left text-sm ui-text-primary hover:bg-[var(--surface-3)]"
            >
              {c.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mt-3 w-full rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-xs ui-text-secondary hover:bg-[var(--surface-3)]"
        >
          暂不选择
        </button>
      </div>
    </div>
  );
}
