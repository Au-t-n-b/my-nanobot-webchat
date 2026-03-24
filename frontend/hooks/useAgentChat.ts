"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const THREAD_STORAGE_KEY = "nanobot_agui_thread_id";

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export type StepLog = {
  id: string;
  stepName: "thinking" | "tool";
  text: string;
};

export type ToolPendingPayload = {
  threadId: string;
  runId: string;
  toolCallId: string;
  toolName: string;
  arguments: string;
};

export type ChoiceItem = { label: string; value: string };

function parseSseRecord(raw: string): { event: string; data: Record<string, unknown> } | null {
  let event = "";
  let dataStr = "";
  for (const line of raw.split("\n")) {
    const t = line.trimEnd();
    if (t.startsWith("event:")) event = t.slice(6).trim();
    else if (t.startsWith("data:")) dataStr = t.slice(5).trim();
  }
  if (!event || !dataStr) return null;
  try {
    return { event, data: JSON.parse(dataStr) as Record<string, unknown> };
  } catch {
    return null;
  }
}

function newId(): string {
  return crypto.randomUUID();
}

function applySseBlocks(
  buffer: string,
  onBlock: (rec: { event: string; data: Record<string, unknown> }) => void,
): string {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const block of parts) {
    const rec = parseSseRecord(block);
    if (rec) onBlock(rec);
  }
  return rest;
}

export function useAgentChat() {
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [stepLogs, setStepLogs] = useState<StepLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingTool, setPendingTool] = useState<ToolPendingPayload | null>(null);
  const [pendingChoices, setPendingChoices] = useState<ChoiceItem[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let tid = localStorage.getItem(THREAD_STORAGE_KEY);
    if (!tid) {
      tid = crypto.randomUUID();
      localStorage.setItem(THREAD_STORAGE_KEY, tid);
    }
    setThreadId(tid);
  }, []);

  const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(
    /\/$/,
    "",
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setStepLogs([]);
    setError(null);
    setPendingTool(null);
    setPendingChoices(null);
  }, []);

  const approveTool = useCallback(
    async (approved: boolean) => {
      if (!pendingTool) return;
      const res = await fetch(`${apiBase}/api/approve-tool`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          threadId: pendingTool.threadId,
          runId: pendingTool.runId,
          toolCallId: pendingTool.toolCallId,
          approved,
        }),
      });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const j = (await res.json()) as { detail?: string };
          if (j?.detail) msg = j.detail;
        } catch {
          // ignore
        }
        setError(msg);
      } else {
        setPendingTool(null);
      }
    },
    [apiBase, pendingTool],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !threadId || isLoading) return;

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      setError(null);
      setPendingTool(null);
      setPendingChoices(null);
      setIsLoading(true);

      const userId = newId();
      const asstId = newId();

      const bodyMessages = [
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user" as const, content: trimmed },
      ];

      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: trimmed },
        { id: asstId, role: "assistant", content: "" },
      ]);

      const runId = crypto.randomUUID();

      const rollbackNewTurn = () => {
        setMessages((prev) => prev.filter((m) => m.id !== asstId && m.id !== userId));
      };

      try {
        const res = await fetch(`${apiBase}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: ac.signal,
          body: JSON.stringify({
            threadId,
            runId,
            messages: bodyMessages,
            humanInTheLoop: true,
          }),
        });

        if (res.status === 409) {
          setError("该会话已有请求进行中");
          rollbackNewTurn();
          return;
        }

        if (!res.ok) {
          let msg = `HTTP ${res.status}`;
          try {
            const j = (await res.json()) as { detail?: string };
            if (j?.detail) msg = j.detail;
          } catch {
            const t = await res.text();
            if (t) msg = t;
          }
          setError(msg);
          rollbackNewTurn();
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          setError("无响应流");
          rollbackNewTurn();
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        const handleRec = (event: string, data: Record<string, unknown>) => {
          if (event === "TextMessageContent" && typeof data.delta === "string") {
            const d = data.delta;
            setMessages((prev) =>
              prev.map((m) => (m.id === asstId ? { ...m, content: m.content + d } : m)),
            );
          } else if (event === "StepStarted" && typeof data.text === "string") {
            const stepName = data.stepName === "tool" ? "tool" : "thinking";
            setStepLogs((prev) => [...prev, { id: newId(), stepName, text: String(data.text) }]);
          } else if (event === "ToolPending") {
            setPendingTool({
              threadId: String(data.threadId ?? ""),
              runId: String(data.runId ?? ""),
              toolCallId: String(data.toolCallId ?? ""),
              toolName: String(data.toolName ?? ""),
              arguments:
                typeof data.arguments === "string"
                  ? data.arguments
                  : JSON.stringify(data.arguments ?? ""),
            });
          } else if (event === "RunFinished") {
            if (Array.isArray(data.choices)) {
              setPendingChoices(data.choices as ChoiceItem[]);
            }
            if (data.error && typeof data.error === "object" && data.error !== null) {
              const err = data.error as { code?: string; message?: string };
              setError(err.message ?? err.code ?? "Unknown error");
            }
          } else if (event === "Error") {
            if (typeof data.message === "string") setError(data.message);
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          buffer = applySseBlocks(buffer, (rec) => handleRec(rec.event, rec.data));
        }
        if (buffer.trim()) {
          const rec = parseSseRecord(buffer);
          if (rec) handleRec(rec.event, rec.data);
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setError(e instanceof Error ? e.message : String(e));
        rollbackNewTurn();
      } finally {
        setIsLoading(false);
      }
    },
    [apiBase, threadId, isLoading, messages],
  );

  return {
    threadId,
    messages,
    stepLogs,
    isLoading,
    error,
    pendingTool,
    pendingChoices,
    sendMessage,
    approveTool,
    clearChat,
  };
}
