"use client";

import type { SduiAction } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

type Props = {
  label?: string | null;
  variant?: "primary" | "secondary" | "ghost";
  action?: SduiAction;
};

const variantClass: Record<NonNullable<Props["variant"]>, string> = {
  primary:
    "bg-slate-900 text-white shadow-sm hover:bg-slate-800 hover:shadow-md dark:bg-white dark:text-slate-900",
  secondary: "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300 shadow-sm",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900",
};

export function SduiButton({ label, variant = "primary", action }: Props) {
  const { postToAgent, openPreview } = useSkillUiRuntime();

  const onClick = () => {
    if (!action) return;
    if (action.kind === "post_user_message") {
      postToAgent(action.text);
    } else if (action.kind === "open_preview") {
      openPreview(action.path);
    }
  };

  return (
    <button
      type="button"
      className={`rounded-lg px-3 py-1.5 text-sm font-medium active:scale-[0.98] transition-all duration-200 flex items-center justify-center gap-2 ${variantClass[variant]}`.trim()}
      onClick={onClick}
    >
      {label ?? ""}
    </button>
  );
}
