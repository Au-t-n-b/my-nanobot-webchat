"use client";

import { useState } from "react";
import { useAgentChat } from "@/hooks/useAgentChat";

export default function Home() {
  const { threadId, messages, isLoading, error, pendingTool, pendingChoices, sendMessage } =
    useAgentChat();
  const [input, setInput] = useState("");

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 flex flex-col gap-4 max-w-2xl mx-auto">
      <header>
        <h1 className="text-xl font-semibold">Nanobot AGUI</h1>
        <p className="text-zinc-500 text-sm mt-1">
          threadId: {threadId || "…"} · API:{" "}
          {process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765"}
        </p>
        <p className="text-zinc-600 text-xs mt-2">
          先在本机运行 <code className="text-zinc-400">nanobot agui -p 8765</code>（联调可用{" "}
          <code className="text-zinc-400">--fake</code>）。再执行{" "}
          <code className="text-zinc-400">npm run dev</code>。
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/50 text-red-200 text-sm px-3 py-2">
          {error}
        </div>
      )}

      {pendingTool && (
        <div className="rounded-md border border-amber-800 bg-amber-950/40 text-amber-100 text-sm px-3 py-2">
          [ToolPending] {pendingTool.toolName} — Step 4 将接 /api/approve-tool
        </div>
      )}

      {pendingChoices && pendingChoices.length > 0 && (
        <div className="rounded-md border border-violet-800 bg-violet-950/40 text-violet-100 text-sm px-3 py-2">
          [choices] Step 5 Modal — {pendingChoices.map((c) => c.label).join(", ")}
        </div>
      )}

      <ul className="flex-1 space-y-3 overflow-y-auto min-h-[200px]">
        {messages.map((m) => (
          <li
            key={m.id}
            className={
              m.role === "user"
                ? "ml-8 rounded-lg bg-zinc-800 px-3 py-2 text-sm"
                : "mr-8 rounded-lg border border-zinc-800 px-3 py-2 text-sm whitespace-pre-wrap"
            }
          >
            {m.content || (isLoading && m.role === "assistant" ? "…" : "")}
          </li>
        ))}
      </ul>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void sendMessage(input);
          setInput("");
        }}
      >
        <input
          className="flex-1 rounded-md bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm outline-none focus:border-zinc-500"
          placeholder="输入消息…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoading || !threadId}
        />
        <button
          type="submit"
          disabled={isLoading || !threadId}
          className="rounded-md bg-zinc-100 text-zinc-900 px-4 py-2 text-sm font-medium disabled:opacity-40"
        >
          {isLoading ? "…" : "发送"}
        </button>
      </form>
    </div>
  );
}
