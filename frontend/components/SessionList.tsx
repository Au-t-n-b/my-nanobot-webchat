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
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          会话 <span className="font-normal normal-case tracking-normal opacity-90">Sessions</span>
        </span>
        <button
          type="button"
          onClick={onCreate}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-medium transition-colors hover:bg-[var(--surface-3)] text-[var(--text-secondary)] hover:text-[var(--accent)]"
          aria-label="创建新会话"
          title="创建新会话"
        >
          <MessageSquarePlus size={11} />
          新建
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
                "group relative w-full rounded-md px-2.5 py-2 text-left transition-colors cursor-pointer outline-none border border-transparent " +
                (active
                  ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]/35"
                  : "hover:bg-[var(--surface-3)]")
              }
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium ui-text-primary">{session.title}</span>
                <span className="inline-flex items-center gap-1 text-[10px] ui-text-muted shrink-0">
                  <Clock3 size={10} />
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
                  className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity rounded p-1 ui-text-muted hover:text-red-500 hover:bg-[var(--surface-2)]"
                  aria-label="删除会话"
                  title="删除会话"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
