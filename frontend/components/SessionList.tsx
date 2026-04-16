"use client";

import { useState } from "react";
import { Clock3, MessageSquarePlus, Trash2 } from "lucide-react";
import type { SessionSummary } from "@/hooks/useAgentChat";
import { CenteredConfirmModal } from "@/components/CenteredModal";
import { SIDEBAR_MODULE_SHELL_CLASS, SIDEBAR_SECTION_LABEL_CLASS } from "@/lib/sidebarTokens";

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
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const pendingSession = pendingDeleteId ? sessions.find((s) => s.id === pendingDeleteId) : null;

  return (
    <>
      <section className={SIDEBAR_MODULE_SHELL_CLASS}>
        <div className="flex items-center justify-between gap-2">
          <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>会话列表</span>
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex items-center justify-center rounded-lg p-2 text-[11px] font-bold uppercase tracking-wide transition-colors text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900/40"
            aria-label="创建新会话"
            title="创建新会话"
          >
            <MessageSquarePlus size={20} strokeWidth={2} aria-hidden />
          </button>
        </div>

        <div className="max-h-[min(300px,44dvh)] min-h-0 overflow-y-auto space-y-0.5 pr-0 [overscroll-behavior-y:auto]">
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
                  (active ? "bg-zinc-900" : "hover:bg-zinc-900/40")
                }
              >
                {active ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.4)] rounded-r"
                  />
                ) : null}
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={
                      "truncate text-sm font-medium " +
                      (active ? "text-zinc-100" : "text-zinc-600 dark:text-zinc-400")
                    }
                  >
                    {session.title}
                  </span>
                  <span
                    className={
                      "inline-flex items-center gap-1 font-mono text-[9px] shrink-0 " +
                      (active ? "opacity-70 text-zinc-200" : "opacity-40 text-zinc-500 dark:text-zinc-500")
                    }
                  >
                    <Clock3 size={18} strokeWidth={active ? 2.25 : 1.75} />
                    {formatUpdatedAt(session.updatedAt)}
                  </span>
                </div>
                <p
                  className={
                    "mt-1 truncate text-[11px] " +
                    (active ? "text-zinc-400" : "text-zinc-600 dark:text-zinc-500")
                  }
                >
                  {session.preview}
                </p>

                {onDelete && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDeleteId(session.id);
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

      <CenteredConfirmModal
        open={Boolean(pendingDeleteId && pendingSession)}
        title="删除会话"
        description={
          pendingSession ? (
            <p>
              确定删除会话「<span className="ui-text-primary font-medium">{pendingSession.title}</span>」？此操作不可撤销。
            </p>
          ) : null
        }
        variant="danger"
        confirmText="删除"
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => {
          if (pendingDeleteId && onDelete) onDelete(pendingDeleteId);
          setPendingDeleteId(null);
        }}
      />
    </>
  );
}
