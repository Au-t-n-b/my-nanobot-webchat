"use client";

import type { AgentMessage } from "@/hooks/useAgentChat";
import { AgentMarkdown } from "@/components/AgentMarkdown";

type Props = {
  messages: AgentMessage[];
  isLoading: boolean;
  onPreviewPath?: (path: string) => void;
};

export function MessageList({ messages, isLoading, onPreviewPath }: Props) {
  return (
    <ul className="flex-1 space-y-3 overflow-y-auto min-h-[320px] pr-1">
      {messages.map((m) => (
        <li
          key={m.id}
          className={
            m.role === "user"
              ? "ml-12 rounded-xl bg-zinc-800 px-3 py-2 text-sm"
              : "mr-12 rounded-xl border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm"
          }
        >
          {m.role === "assistant" ? (
            <AgentMarkdown
              content={m.content || (isLoading ? "…" : "")}
              onPreviewPath={onPreviewPath}
            />
          ) : (
            <span className="whitespace-pre-wrap">{m.content}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
