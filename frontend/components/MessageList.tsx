"use client";

import type { AgentMessage } from "@/hooks/useAgentChat";

type Props = {
  messages: AgentMessage[];
  isLoading: boolean;
};

export function MessageList({ messages, isLoading }: Props) {
  return (
    <ul className="flex-1 space-y-3 overflow-y-auto min-h-[320px] pr-1">
      {messages.map((m) => (
        <li
          key={m.id}
          className={
            m.role === "user"
              ? "ml-12 rounded-xl bg-zinc-800 px-3 py-2 text-sm"
              : "mr-12 rounded-xl border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm whitespace-pre-wrap"
          }
        >
          {m.content || (isLoading && m.role === "assistant" ? "…" : "")}
        </li>
      ))}
    </ul>
  );
}
