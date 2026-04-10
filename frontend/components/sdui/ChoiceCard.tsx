"use client";

import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import type { SduiChoiceOption } from "@/lib/sdui";

type Props = {
  title: string;
  options: SduiChoiceOption[];
  cardId?: string;
};

export function SduiChoiceCard({ title, options, cardId }: Props) {
  const runtime = useSkillUiRuntime();
  const [selected, setSelected] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const confirm = () => {
    if (!selected || !cardId) return;
    setConfirmed(true);
    runtime.postToAgent?.(
      JSON.stringify({ type: "chat_card_intent", verb: "choice_selected", cardId, payload: { optionId: selected } })
    );
  };

  return (
    <div
      className="rounded-lg overflow-hidden border"
      style={{
        background: "color-mix(in oklab, var(--warning) 6%, var(--surface-1))",
        borderColor: "color-mix(in oklab, var(--warning) 25%, transparent)",
        borderLeft: "3px solid var(--warning)",
      }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 border-b"
        style={{ borderColor: "color-mix(in oklab, var(--warning) 15%, transparent)" }}
      >
        <span className="text-[10px] font-bold tracking-wide uppercase" style={{ color: "var(--warning)" }}>
          需要你的输入 · 选项确认
        </span>
      </div>
      <div className="px-3 py-2.5 space-y-2.5">
        <p className="text-xs ui-text-secondary">{title}</p>
        <div className="space-y-1.5">
          {options.map((opt) => {
            const isSelected = selected === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                disabled={confirmed}
                onClick={() => setSelected(opt.id)}
                className={[
                  "w-full text-left flex items-center gap-2.5 rounded-md px-3 py-2 text-xs transition-colors border",
                  isSelected
                    ? "border-[var(--accent)] text-[var(--accent)]"
                    : "ui-text-secondary hover:ui-text-primary border-[var(--border-subtle)] hover:border-[var(--accent)]",
                ].join(" ")}
                style={{
                  background: isSelected
                    ? "color-mix(in oklab, var(--accent) 10%, var(--surface-2))"
                    : "var(--surface-2)",
                }}
              >
                <span
                  className="w-3.5 h-3.5 rounded-full border flex-shrink-0 flex items-center justify-center"
                  style={{
                    borderColor: isSelected ? "var(--accent)" : "var(--border-subtle)",
                    background: isSelected ? "var(--accent)" : "transparent",
                  }}
                >
                  {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
                </span>
                {opt.label}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          disabled={!selected || confirmed}
          onClick={confirm}
          className="w-full rounded-md py-2 text-xs font-semibold text-white disabled:opacity-40 transition-opacity"
          style={{ background: "var(--accent)" }}
        >
          {confirmed ? (
            <span className="flex items-center justify-center gap-1.5">
              <CheckCircle2 size={13} /> 已确认
            </span>
          ) : (
            "确认选择"
          )}
        </button>
      </div>
    </div>
  );
}
