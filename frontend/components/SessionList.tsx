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
  /** 当父级已提供主 CTA "新建会话" 时，隐藏组件内重复的 + 按钮 */
  hideCreate?: boolean;
};

function formatUpdatedAt(ts: number): string {
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function SessionList({ currentThreadId, sessions, onCreate, onSelect, onDelete, hideCreate }: Props) {
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const pendingSession = pendingDeleteId ? sessions.find((s) => s.id === pendingDeleteId) : null;

  return (
    <>
      <section className={SIDEBAR_MODULE_SHELL_CLASS}>
        <div className="flex items-center justify-between gap-2">
          <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>会话</span>
          {hideCreate ? null : (
            <button
              type="button"
              onClick={onCreate}
              className="inline-flex items-center justify-center rounded-lg p-2 text-[10px] font-medium tracking-[0.12em] ui-text-muted ui-hover-soft"
              aria-label="创建新会话"
              title="创建新会话"
            >
              <MessageSquarePlus size={18} strokeWidth={2} aria-hidden />
            </button>
          )}
        </div>

        <div className="max-h-[min(320px,44dvh)] min-h-0 overflow-y-auto space-y-0 pr-0 [overscroll-behavior-y:auto] [scrollbar-width:thin]">
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
                  "group relative w-full rounded-lg px-3 py-2 text-left ui-motion-fast cursor-pointer outline-none border border-transparent " +
                  (active ? "bg-[var(--surface-1)]" : "ui-hover-soft")
                }
              >
                {active ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-[var(--accent)]"
                  />
                ) : null}
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={
                      "truncate text-[12px] font-medium " +
                      (active ? "ui-text-primary" : "ui-text-secondary")
                    }
                  >
                    {session.title}
                  </span>
                  <span
                    className={
                      "inline-flex items-center gap-1 font-mono text-[10px] shrink-0 " +
                      (active ? "opacity-70 ui-text-primary" : "opacity-40 ui-text-muted")
                    }
                  >
                    <Clock3 size={16} strokeWidth={active ? 2.25 : 1.75} />
                    {formatUpdatedAt(session.updatedAt)}
                  </span>
                </div>
                <p
                  className={
                    "mt-1 truncate text-[10px] " +
                    (active ? "ui-text-secondary" : "ui-text-muted")
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
                    className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 ui-motion-fast rounded p-1 ui-text-muted hover:!text-[var(--danger)] hover:!bg-[color-mix(in_oklab,var(--danger)_10%,transparent)]"
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
