"use client";

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
}: Props) {
  const inlineStatusTag =
    !isLoading && runStatus === "completed" && statusMessage === "本轮执行完成"
      ? "本轮执行完成"
      : null;

  return (
    <section className="h-full min-h-0 overflow-hidden p-4 flex flex-col gap-3 bg-transparent border-0 shadow-none">

      {pendingTool && (
        <div className="rounded-xl px-3 py-3 text-sm" style={{ border: "1px solid rgba(247,184,75,0.32)", background: "rgba(247,184,75,0.08)" }}>
          <div className="font-medium ui-status-warning">等待确认工具：{pendingTool.toolName}</div>
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

      {pendingChoices && pendingChoices.length > 0 && (
        <div className="rounded-xl px-3 py-2 text-sm" style={{ border: "1px solid rgba(124,196,250,0.22)", background: "rgba(124,196,250,0.08)" }}>
          <span className="ui-text-secondary">系统已生成下一步选项：</span> {pendingChoices.map((c) => c.label).join("、")}
        </div>
      )}

      <StepLogs stepLogs={stepLogs} runStatus={runStatus} statusMessage={statusMessage} runModel={effectiveModel} />
      <MessageList
        messages={messages}
        isLoading={isLoading}
        inlineStatusTag={inlineStatusTag ?? undefined}
        onFileLinkClick={onFileLinkClick}
        onDeleteMessage={onDeleteMessage}
        searchQuery={searchQuery}
      />
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
