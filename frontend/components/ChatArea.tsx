"use client";

import type { AgentMessage, ChoiceItem, StepLog, ToolPendingPayload } from "@/hooks/useAgentChat";
import { MessageList } from "@/components/MessageList";
import { StepLogs } from "@/components/StepLogs";
import { ChatInput } from "@/components/ChatInput";

type Props = {
  messages: AgentMessage[];
  stepLogs: StepLog[];
  isLoading: boolean;
  error: string | null;
  pendingTool: ToolPendingPayload | null;
  pendingChoices: ChoiceItem[] | null;
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
};

export function ChatArea({
  messages,
  stepLogs,
  isLoading,
  error,
  pendingTool,
  pendingChoices,
  input,
  setInput,
  onSend,
  disabled,
}: Props) {
  return (
    <section className="h-full rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 flex flex-col gap-3">
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/50 text-red-200 text-sm px-3 py-2">
          {error}
        </div>
      )}

      {pendingTool && (
        <div className="rounded-md border border-amber-800 bg-amber-950/40 text-amber-100 text-sm px-3 py-2">
          [ToolPending] {pendingTool.toolName} - Step 4 将接 /api/approve-tool
        </div>
      )}

      {pendingChoices && pendingChoices.length > 0 && (
        <div className="rounded-md border border-violet-800 bg-violet-950/40 text-violet-100 text-sm px-3 py-2">
          [choices] Step 5 Modal - {pendingChoices.map((c) => c.label).join(", ")}
        </div>
      )}

      <StepLogs stepLogs={stepLogs} />
      <MessageList messages={messages} isLoading={isLoading} />
      <ChatInput
        value={input}
        onChange={setInput}
        onSubmit={onSend}
        disabled={disabled}
        loading={isLoading}
      />
    </section>
  );
}
