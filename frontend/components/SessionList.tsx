"use client";

import { Clock3, MessageSquarePlus, Trash2 } from "lucide-react";
import type { SessionSummary } from "@/hooks/useAgentChat";

type Props = {
  currentThreadId: string;
  sessions: SessionSummary[];
  onCreate: () => void;
  onSelect: (threadId: string) => void;
  onDelete?: (threadId: string) => void;
};

function formatUpdatedAt(ts: number): string {
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function SessionList({ currentThreadId, sessions, onCreate, onSelect, onDelete }: Props) {
  return (
    <section className="flex flex-col gap-2 min-h-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em]">
          Sessions
        </span>
        <button
          type="button"
          onClick={onCreate}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-bold uppercase tracking-wide transition-colors text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900/40"
          aria-label="创建新会话"
          title="创建新会话"
        >
          <MessageSquarePlus size={18} />
          New
        </button>
      </div>

      <div className="max-h-40 overflow-auto space-y-0.5">
        {sessions.map((session) => {
          const active = session.id === currentThreadId;
          return (
            <div
              key={session.id}
              onClick={() => onSelect(session.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(session.id);
                }
              }}
              role="button"
              tabIndex={0}
              className={
                "group relative w-full rounded-md pl-3 pr-2.5 py-2 text-left transition-colors cursor-pointer outline-none border border-transparent " +
                (active
                  ? "bg-zinc-900"
                  : "hover:bg-zinc-900/40")
              }
            >
              {active ? (
                <span
                  aria-hidden="true"
                  className="absolute left-0 top-1 bottom-1 w-[2px] bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.4)] rounded-r"
                />
              ) : null}
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium ui-text-primary">{session.title}</span>
                <span className="inline-flex items-center gap-1 font-mono text-[9px] opacity-40 shrink-0 text-zinc-200">
                  <Clock3 size={18} strokeWidth={active ? 2.25 : 1.75} />
                  {formatUpdatedAt(session.updatedAt)}
                </span>
              </div>
              <p className="mt-1 truncate text-[11px] ui-text-secondary">{session.preview}</p>

              {onDelete && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm("确定删除该会话？")) onDelete(session.id);
                  }}
                  className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity rounded p-1 text-zinc-500 hover:text-red-400 hover:bg-zinc-900/40"
                  aria-label="删除会话"
                  title="删除会话"
                >
                  <Trash2 size={18} strokeWidth={active ? 2.25 : 1.75} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
