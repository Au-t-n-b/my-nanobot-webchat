"use client";

import { Bot, Cpu, FileText, Sparkles } from "lucide-react";

type Props = {
  threadId: string;
  apiBase: string;
  onClear: () => void;
};

export function Sidebar({ threadId, apiBase, onClear }: Props) {
  return (
    <aside className="h-full rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex flex-col gap-4">
      <div className="flex items-center gap-2 text-zinc-100 font-semibold">
        <Bot size={16} />
        <span>Nanobot AGUI</span>
      </div>

      <div className="text-xs text-zinc-500 space-y-2">
        <p>threadId</p>
        <p className="break-all text-zinc-300">{threadId || "..."}</p>
        <p className="pt-1">API</p>
        <p className="break-all text-zinc-400">{apiBase}</p>
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center gap-2 text-zinc-400"><Cpu size={14} /> 模型：当前后端配置</div>
        <div className="flex items-center gap-2 text-zinc-400"><Sparkles size={14} /> 技能：Task4/5/6 继续接入</div>
        <div className="flex items-center gap-2 text-zinc-400"><FileText size={14} /> 文件索引：Task6 预览接入</div>
      </div>

      <button
        type="button"
        onClick={onClear}
        className="mt-auto rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800"
      >
        清空当前对话
      </button>
    </aside>
  );
}
