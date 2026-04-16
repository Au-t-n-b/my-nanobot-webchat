"use client";

import type { SduiAction } from "@/lib/sdui";
import type { SduiSemanticColor } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { semanticBgClass, semanticTextClass } from "@/components/sdui/sduiSemanticColor";

type Props = {
  label?: string | null;
  variant?: "primary" | "secondary" | "ghost" | "outline";
  color?: SduiSemanticColor;
  action?: SduiAction;
};

const variantClass: Record<NonNullable<Props["variant"]>, string> = {
  primary:
    "bg-slate-900 text-white shadow-sm hover:bg-slate-800 hover:shadow-md dark:bg-white dark:text-slate-900",
  secondary: "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300 shadow-sm",
  ghost:
    "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]",
  outline:
    "border border-[var(--border-strong)] bg-transparent text-[var(--text-primary)] hover:bg-[var(--surface-3)] shadow-sm",
};

export function SduiButton({ label, variant = "primary", color, action }: Props) {
  const { postToAgent, openPreview } = useSkillUiRuntime();

  const onClick = () => {
    if (!action) return;
    if (action.kind === "post_user_message") {
      postToAgent(action.text);
    } else if (action.kind === "open_preview") {
      openPreview(action.path);
    } else {
      console.warn("[SDUI] unknown button action kind:", (action as { kind?: unknown })?.kind);
    }
  };

  return (
    <button
      type="button"
      className={[
        "rounded-lg px-3 py-1.5 text-sm font-medium active:scale-[0.98] transition-all duration-200 flex items-center justify-center gap-2",
        variantClass[variant],
        // v2：语义色（accent 固定蓝色，不走主题 var(--accent)）
        (variant === "primary" && color)
          ? `${semanticBgClass(color)} text-white shadow-sm hover:opacity-95`
          : "",
        (variant !== "primary" && color)
          ? `${semanticTextClass(color)}`
          : "",
      ].join(" ").trim()}
      onClick={onClick}
    >
      {label ?? ""}
    </button>
  );
}
