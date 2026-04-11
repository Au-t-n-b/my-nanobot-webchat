"use client";

import { Zap } from "lucide-react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import type { SduiGuidanceAction } from "@/lib/sdui";

type Props = {
  context: string;
  actions: SduiGuidanceAction[];
  cardId?: string;
};

export function SduiGuidanceCard({ context, actions, cardId }: Props) {
  const runtime = useSkillUiRuntime();

  return (
    <div
      className="rounded-lg overflow-hidden border"
      style={{
        background: "color-mix(in oklab, var(--accent) 8%, var(--surface-1))",
        borderColor: "color-mix(in oklab, var(--accent) 25%, transparent)",
        borderLeft: "3px solid var(--accent)",
      }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2 border-b"
        style={{ borderColor: "color-mix(in oklab, var(--accent) 15%, transparent)" }}
      >
        <Zap size={12} style={{ color: "var(--accent)" }} />
        <span className="text-[10px] font-bold tracking-wide uppercase" style={{ color: "var(--accent)" }}>
          引导 · Claw
        </span>
      </div>
      <div className="px-3 py-2.5 space-y-2.5">
        <p className="text-xs ui-text-secondary leading-relaxed">{context}</p>
        {actions.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {actions.map((a, i) => (
              <button
                key={`${a.verb}-${i}`}
                type="button"
                onClick={() => {
                  if (!cardId) return;
                  runtime.postToAgent?.(
                    JSON.stringify({
                      type: "chat_card_intent",
                      verb: a.verb,
                      cardId,
                      payload: a.payload !== undefined ? a.payload : null,
                    })
                  );
                }}
                className={[
                  "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                  i === 0
                    ? "text-white hover:opacity-90"
                    : "border ui-text-muted hover:ui-text-primary hover:bg-[var(--surface-3)]",
                ].join(" ")}
                style={i === 0 ? { background: "var(--accent)" } : { borderColor: "var(--border-subtle)" }}
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
