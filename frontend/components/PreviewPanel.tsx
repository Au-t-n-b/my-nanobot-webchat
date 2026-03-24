"use client";

import { Eye, EyeOff } from "lucide-react";

type Props = {
  visible: boolean;
  onToggle: () => void;
};

export function PreviewPanel({ visible, onToggle }: Props) {
  if (!visible) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="h-full rounded-xl border border-zinc-800 bg-zinc-900/40 text-zinc-400 text-sm px-3"
      >
        <span className="inline-flex items-center gap-2"><Eye size={14} /> 打开预览栏</span>
      </button>
    );
  }

  return (
    <aside className="h-full rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-200">Preview Panel</h2>
        <button type="button" onClick={onToggle} className="text-zinc-400 hover:text-zinc-200">
          <EyeOff size={14} />
        </button>
      </div>
      <div className="flex-1 rounded-md border border-dashed border-zinc-700 text-zinc-500 text-sm p-3">
        Task 6 将在这里接入文件预览（HTML/PDF/Markdown/Excel/Word/Mermaid）。
      </div>
    </aside>
  );
}
