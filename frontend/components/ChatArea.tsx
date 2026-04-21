"use client";

import { useEffect } from "react";
import type { AgentMessage, ChoiceItem, RunStatus, StepLog, ToolPendingPayload } from "@/hooks/useAgentChat";
import { MessageList } from "@/components/MessageList";
import { StepLogs } from "@/components/StepLogs";
import { ChatInput } from "@/components/ChatInput";
import type { SduiUploadedFileRecord } from "@/lib/sdui";
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
  chatCardPostToAgent?: (text: string) => void | Promise<void>;
  /** ChatCard 内静默唤醒（不入消息流） */
  chatCardPostToAgentSilently?: (text: string) => void | Promise<void>;
  /** present_choices：在消息流内联卡片时，允许卡片发送纯文本回主输入 */
  chatCardOnSendText?: (text: string, opts?: { cardId?: string; submittedValue?: string }) => void;
  /** FilePicker：将提交态与 uploads 写回聊天历史，支持刷新回放 */
  chatCardOnLockFilePicker?: (cardId: string, uploads: SduiUploadedFileRecord[]) => void;
  /** Skill-First 混合模式：来自 TaskStatusUpdate 的 `hybrid:*` 模块摘要 */
  hybridSubtaskHint?: string | null;
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
  chatCardPostToAgentSilently,
  chatCardOnSendText,
  chatCardOnLockFilePicker,
  hybridSubtaskHint = null,
}: Props) {
  const last = messages[messages.length - 1];
  const showStreamCaret = Boolean(
    isLoading && last && last.role === "assistant" && (last.content?.trim()?.length ?? 0) > 0,
  );

  useEffect(() => {
    // no-op: present_choices is rendered as an inline ChoiceCard in the message stream
  }, []);

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
        hybridSubtaskHint={hybridSubtaskHint}
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
        chatCardPostToAgentSilently={chatCardPostToAgentSilently}
        chatCardOnSendText={chatCardOnSendText}
        chatCardOnLockFilePicker={chatCardOnLockFilePicker}
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
