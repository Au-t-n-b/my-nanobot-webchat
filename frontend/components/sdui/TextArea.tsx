"use client";

import { useEffect } from "react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

type Props = {
  inputId?: string | null;
  label?: string;
  placeholder?: string;
  rows?: number;
  defaultValue?: string;
};

export function SduiTextArea({ inputId, label, placeholder, rows = 4, defaultValue = "" }: Props) {
  const { getInputValue, setInputValue, syncState } = useSkillUiRuntime();
  const id = inputId?.trim() || "_sdui_textarea";

  useEffect(() => {
    const cur = getInputValue(id);
    if (cur === defaultValue) return;
    setInputValue(id, defaultValue);
  }, [id, defaultValue, getInputValue, setInputValue]);

  const value = getInputValue(id);

  return (
    <label className="block min-w-0">
      {label ? (
        <span className="block text-sm font-medium text-slate-700 mb-2 dark:text-[var(--text-secondary)]">{label}</span>
      ) : null}
      <textarea
        className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-300 transition-all resize-y min-h-[4rem] dark:border-white/10 dark:bg-[var(--surface-2)]/50 dark:text-[var(--text-primary)] dark:focus:bg-[var(--surface-1)] dark:focus:ring-white/10"
        rows={rows}
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          setInputValue(id, v);
          syncState({ key: `inputs.${id}`, value: v, behavior: "debounce" });
        }}
      />
    </label>
  );
}
