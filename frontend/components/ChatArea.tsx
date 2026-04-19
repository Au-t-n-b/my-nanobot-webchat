"use client";

import { useEffect } from "react";
import type { AgentMessage, ChoiceItem, RunStatus, StepLog, ToolPendingPayload } from "@/hooks/useAgentChat";
import { MessageList } from "@/components/MessageList";
import { StepLogs } from "@/components/StepLogs";
import { ChatInput } from "@/components/ChatInput";
type Props = {
  messages: AgentMessage[];
  stepLogs: StepLog[];
  isLoading: boolean;
  runStatus: RunStatus;
  statusMessage: string;
  effectiveModel?: string | null;
  pendingTool: ToolPendingPayload | null;
  pendingChoices: ChoiceItem[] | null;
  onSend: (value: string) => void;
  onStop?: () => void;
  onApproveTool: (approved: boolean) => void;
  onFileLinkClick?: (path: string) => void;
  onDeleteMessage?: (id: string) => void;
  searchQuery?: string;
  disabled: boolean;
  focusSignal?: number;
  prefillText?: string;
  /** ChatCard 内 HITL 回传（JSON chat_card_intent） */
  chatCardPostToAgent?: (text: string) => void;
  /** present_choices 工具：在会话内嵌选项（不再使用全屏弹窗） */
  onSelectPendingChoice?: (choice: ChoiceItem) => void;
  onDismissPendingChoices?: () => void;
};

export function ChatArea({
  messages,
  stepLogs,
  isLoading,
  runStatus,
  statusMessage,
  effectiveModel,
  pendingTool,
  pendingChoices,
  onSend,
  onStop,
  onApproveTool,
  onFileLinkClick,
  onDeleteMessage,
  searchQuery,
  disabled,
  focusSignal,
  prefillText,
  chatCardPostToAgent,
  onSelectPendingChoice,
  onDismissPendingChoices,
}: Props) {
  const showQuickReplies =
    Boolean(pendingChoices && pendingChoices.length > 0 && onSelectPendingChoice && onDismissPendingChoices);

  const last = messages[messages.length - 1];
  const showStreamCaret = Boolean(
    isLoading && last && last.role === "assistant" && (last.content?.trim()?.length ?? 0) > 0,
  );

  useEffect(() => {
    if (!showQuickReplies || !pendingChoices?.length || !onSelectPendingChoice) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement) return;
      const n = Number.parseInt(e.key, 10);
      if (n >= 1 && n <= 9 && pendingChoices[n - 1]) {
        e.preventDefault();
        onSelectPendingChoice(pendingChoices[n - 1]!);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showQuickReplies, pendingChoices, onSelectPendingChoice]);

  return (
    <section className="h-full min-h-0 overflow-hidden p-4 flex flex-col gap-3 bg-transparent border-0 shadow-none">

      {pendingTool && (
        <div
          className="rounded-xl border px-3 py-3 text-sm border-[color-mix(in_oklab,var(--accent)_28%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--accent)_6%,var(--surface-1))]"
        >
          <div className="font-medium text-[var(--accent)]">等待确认工具：{pendingTool.toolName}</div>
          <div className="ui-text-secondary mt-1 break-all">{pendingTool.arguments}</div>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => onApproveTool(true)}
              className="rounded-lg px-3 py-1.5 text-xs text-white"
              style={{ background: "var(--success)" }}
            >
              运行
            </button>
            <button
              type="button"
              onClick={() => onApproveTool(false)}
              className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs"
            >
              取消
            </button>
          </div>
        </div>
      )}

      <StepLogs
        stepLogs={stepLogs}
        runStatus={runStatus}
        statusMessage={statusMessage}
        runModel={effectiveModel}
        isLoading={isLoading}
      />
      <MessageList
        messages={messages}
        isLoading={isLoading}
        showStreamingCaret={showStreamCaret}
        inlineStatusTag={undefined}
        onFileLinkClick={onFileLinkClick}
        onDeleteMessage={onDeleteMessage}
        searchQuery={searchQuery}
        chatCardPostToAgent={chatCardPostToAgent}
      />
      {showQuickReplies ? (
        <div className="shrink-0">
          <div className="mb-2 flex items-center justify-between gap-3 px-1">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] ui-text-muted">
              Quick Actions
            </span>
            <span className="text-[11px] ui-text-muted">点击后作为下一条消息发送</span>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {pendingChoices!.map((choice, idx) => (
              <button
                key={`${choice.value}:${choice.label}`}
                type="button"
                onClick={() => onSelectPendingChoice?.(choice)}
                className="shrink-0 inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-2 text-sm ui-text-primary shadow-[var(--shadow-card)] transition-all hover:-translate-y-px hover:border-[color-mix(in_srgb,var(--accent)_45%,transparent)] hover:bg-[var(--surface-2)]"
              >
                {idx < 9 ? (
                  <kbd className="rounded border border-[var(--border-subtle)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[10px] ui-text-muted">
                    {idx + 1}
                  </kbd>
                ) : null}
                <span>{choice.label}</span>
              </button>
            ))}
            <button
              type="button"
              onClick={() => onDismissPendingChoices?.()}
              className="shrink-0 rounded-full border border-dashed border-[var(--border-subtle)] bg-transparent px-4 py-2 text-sm ui-text-secondary transition-colors hover:bg-[var(--surface-1)] hover:ui-text-primary"
            >
              暂不选择
            </button>
          </div>
        </div>
      ) : null}
      <ChatInput
        onSubmit={onSend}
        onStop={onStop}
        disabled={disabled}
        loading={isLoading}
        focusSignal={focusSignal}
        prefillText={prefillText}
      />
    </section>
  );
}
