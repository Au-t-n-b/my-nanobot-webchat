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
  const { getInputValue, setInputValue } = useSkillUiRuntime();
  const id = inputId?.trim() || "_sdui_textarea";

  useEffect(() => {
    setInputValue(id, defaultValue);
  }, [id, defaultValue, setInputValue]);

  const value = getInputValue(id);

  return (
    <label className="block min-w-0">
      {label ? (
        <span className="block text-sm font-medium text-slate-700 mb-2 dark:text-zinc-300">{label}</span>
      ) : null}
      <textarea
        className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-300 transition-all resize-y min-h-[4rem] dark:border-white/10 dark:bg-zinc-800/50 dark:text-zinc-100 dark:focus:bg-zinc-900 dark:focus:ring-white/10"
        rows={rows}
        placeholder={placeholder}
        value={value}
        onChange={(e) => setInputValue(id, e.target.value)}
      />
    </label>
  );
}
