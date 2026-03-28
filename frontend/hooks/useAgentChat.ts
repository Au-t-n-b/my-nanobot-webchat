"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CURRENT_THREAD_STORAGE_KEY = "nanobot_agui_current_thread_id";
const THREAD_MESSAGES_STORAGE_KEY = "nanobot_agui_messages_by_thread";
const SESSION_SUMMARIES_STORAGE_KEY = "nanobot_agui_sessions";
const LEGACY_MESSAGES_STORAGE_KEY = "nanobot_agui_messages";
const MESSAGES_CAP = 50;
const MESSAGES_MAX_BYTES = 1.8 * 1024 * 1024;
const STREAM_IDLE_TIMEOUT_MS = 20_000;

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** File paths inferred from tool-execution step logs during this message's run */
  artifacts?: string[];
};

export type SessionSummary = {
  id: string;
  title: string;
  preview: string;
  updatedAt: number;
  messageCount: number;
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
export type RunStatus = "idle" | "running" | "awaitingApproval" | "completed" | "error";

function sanitizeMessages(msgs: AgentMessage[]): AgentMessage[] {
  let toSave = msgs
    .filter((m) => m && typeof m.id === "string" && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .slice(-MESSAGES_CAP);
  let serialized = JSON.stringify(toSave);
  while (serialized.length > MESSAGES_MAX_BYTES && toSave.length > 1) {
    toSave = toSave.slice(1);
    serialized = JSON.stringify(toSave);
  }
  return toSave;
}

function loadMessageMap(): Record<string, AgentMessage[]> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(THREAD_MESSAGES_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).map(([threadId, value]) => [
        threadId,
        Array.isArray(value) ? sanitizeMessages(value as AgentMessage[]) : [],
      ]),
    );
  } catch {
    return {};
  }
}

function loadLegacyMessages(): AgentMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(LEGACY_MESSAGES_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? sanitizeMessages(parsed as AgentMessage[]) : [];
  } catch {
    return [];
  }
}

function saveMessageMap(map: Record<string, AgentMessage[]>) {
  if (typeof window === "undefined") return;
  const sanitized = Object.fromEntries(
    Object.entries(map).map(([threadId, msgs]) => [threadId, sanitizeMessages(msgs)]),
  );
  localStorage.setItem(THREAD_MESSAGES_STORAGE_KEY, JSON.stringify(sanitized));
}

function clipText(text: string, max: number): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max - 1)}…` : normalized;
}

function deriveSessionSummary(threadId: string, messages: AgentMessage[], updatedAt = Date.now()): SessionSummary {
  const firstUser = messages.find((m) => m.role === "user" && m.content.trim());
  const lastMessage = [...messages].reverse().find((m) => m.content.trim());
  const titleSource = firstUser?.content || lastMessage?.content || "新对话";
  return {
    id: threadId,
    title: clipText(titleSource, 24),
    preview: lastMessage ? clipText(lastMessage.content, 42) : "还没有消息",
    updatedAt,
    messageCount: messages.length,
  };
}

function loadSessionSummaries(): SessionSummary[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(SESSION_SUMMARIES_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as SessionSummary[])
      .filter((s) => s && typeof s.id === "string")
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

function saveSessionSummaries(summaries: SessionSummary[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(
    SESSION_SUMMARIES_STORAGE_KEY,
    JSON.stringify([...summaries].sort((a, b) => b.updatedAt - a.updatedAt)),
  );
}

function upsertSessionSummary(summaries: SessionSummary[], summary: SessionSummary): SessionSummary[] {
  const next = summaries.filter((item) => item.id !== summary.id);
  next.unshift(summary);
  return next.sort((a, b) => b.updatedAt - a.updatedAt);
}

// ---- path extraction from tool step log text ----
const _FILE_EXT = "(?:mmd|md|markdown|txt|json|ya?ml|toml|csv|pdf|png|jpe?g|gif|webp|svg|xlsx?|docx|html?|xml|log|ini|ts|tsx|js|jsx|py|rs|sh)";
const _WIN_PATH_RE = new RegExp(`([A-Za-z]:[/\\\\][^\\s\`\\]\\)"'\\n]{3,}\\.(?:${_FILE_EXT}))`, "gi");
const _UNIX_PATH_RE = new RegExp(`(\\/(?:home|Users|tmp|var|opt|workspace|root)[^\\s\`\\]\\)"'\\n]{3,}\\.(?:${_FILE_EXT}))`, "gi");
// Catches Python save calls: .save('path'), to_excel('path'), to_csv('path'), open('path',
const _PY_SAVE_RE = /(?:\.save|\.to_excel|\.to_csv|\.write|open)\s*\(\s*["'`]([^"'`\n]{3,})["'`]/gi;

function extractPathsFromToolText(text: string): string[] {
  const found = new Set<string>();
  const tryAdd = (raw: string) => {
    const p = raw.trim();
    if (p.length > 3) found.add(p);
  };
  _WIN_PATH_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = _WIN_PATH_RE.exec(text)) !== null) tryAdd(m[1] ?? "");
  _UNIX_PATH_RE.lastIndex = 0;
  while ((m = _UNIX_PATH_RE.exec(text)) !== null) tryAdd(m[1] ?? "");
  _PY_SAVE_RE.lastIndex = 0;
  while ((m = _PY_SAVE_RE.exec(text)) !== null) {
    const p = (m[1] ?? "").trim();
    // only keep entries that look like file paths (have extension from our list)
    if (/\.[a-z]{2,6}$/i.test(p)) tryAdd(p);
  }
  return Array.from(found);
}

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
  } catch (e) {
    console.error("Failed to parse SSE data JSON:", { error: e, raw, dataStr });
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

/** Browser calls same-origin ``/api/*`` (Next rewrites → AGUI). Set ``NEXT_PUBLIC_AGUI_DIRECT=1`` to hit Python URL directly. */
function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${base}${p}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

export function useAgentChat() {
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [stepLogs, setStepLogs] = useState<StepLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingTool, setPendingTool] = useState<ToolPendingPayload | null>(null);
  const [pendingChoices, setPendingChoices] = useState<ChoiceItem[] | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [statusMessage, setStatusMessage] = useState("准备就绪");
  const [effectiveModel, setEffectiveModel] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const hydratedRef = useRef(false);
  const runStatusRef = useRef<RunStatus>("idle");

  useEffect(() => {
    runStatusRef.current = runStatus;
  }, [runStatus]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const messageMap = loadMessageMap();
    let tid = localStorage.getItem(CURRENT_THREAD_STORAGE_KEY);
    const initialSessions = loadSessionSummaries();
    if (!tid) tid = crypto.randomUUID();
    if (!messageMap[tid]) {
      const legacy = loadLegacyMessages();
      if (legacy.length > 0) {
        messageMap[tid] = legacy;
        saveMessageMap(messageMap);
        localStorage.removeItem(LEGACY_MESSAGES_STORAGE_KEY);
      }
    }
    const ensured = upsertSessionSummary(initialSessions, deriveSessionSummary(tid, messageMap[tid] ?? []));
    localStorage.setItem(CURRENT_THREAD_STORAGE_KEY, tid);
    saveSessionSummaries(ensured);
    setSessions(ensured);
    setThreadId(tid);
    setMessages(messageMap[tid] ?? []);
    hydratedRef.current = true;
  }, []);

  useEffect(() => {
    if (!hydratedRef.current || !threadId) return;
    const messageMap = loadMessageMap();
    messageMap[threadId] = sanitizeMessages(messages);
    saveMessageMap(messageMap);
    const nextSessions = upsertSessionSummary(loadSessionSummaries(), deriveSessionSummary(threadId, messages));
    saveSessionSummaries(nextSessions);
    setSessions(nextSessions);
  }, [messages, threadId]);

  const deleteMessage = useCallback(
    (id: string) => {
      setMessages((prev) => {
        const next = prev.filter((m) => m.id !== id);
        if (threadId) {
          const messageMap = loadMessageMap();
          messageMap[threadId] = sanitizeMessages(next);
          saveMessageMap(messageMap);
          const nextSummaries = upsertSessionSummary(
            loadSessionSummaries(),
            deriveSessionSummary(threadId, next),
          );
          saveSessionSummaries(nextSummaries);
          setSessions(nextSummaries);
        }
        return next;
      });
    },
    [threadId],
  );

  const clearChat = useCallback(() => {
    if (typeof window !== "undefined" && threadId) {
      const messageMap = loadMessageMap();
      messageMap[threadId] = [];
      saveMessageMap(messageMap);
      const nextSessions = upsertSessionSummary(loadSessionSummaries(), deriveSessionSummary(threadId, []));
      saveSessionSummaries(nextSessions);
      setSessions(nextSessions);
    }
    setMessages([]);
    setStepLogs([]);
    setError(null);
    setPendingTool(null);
    setPendingChoices(null);
    setRunStatus("idle");
    setStatusMessage("当前会话已清空");
    setEffectiveModel(null);
  }, [threadId]);

  const clearPendingChoices = useCallback(() => {
    setPendingChoices(null);
  }, []);

  const createSession = useCallback(() => {
    abortRef.current?.abort();
    const nextThreadId = crypto.randomUUID();
    if (typeof window !== "undefined") {
      localStorage.setItem(CURRENT_THREAD_STORAGE_KEY, nextThreadId);
      const nextSessions = upsertSessionSummary(loadSessionSummaries(), deriveSessionSummary(nextThreadId, []));
      saveSessionSummaries(nextSessions);
      setSessions(nextSessions);
    }
    setThreadId(nextThreadId);
    setMessages([]);
    setStepLogs([]);
    setError(null);
    setPendingTool(null);
    setPendingChoices(null);
    setIsLoading(false);
    setRunStatus("idle");
    setStatusMessage("已创建新会话");
    setEffectiveModel(null);
  }, []);

  const deleteSession = useCallback(
    (deleteThreadId: string) => {
      abortRef.current?.abort();
      if (typeof window === "undefined") return;

      const messageMap = loadMessageMap();
      delete messageMap[deleteThreadId];
      saveMessageMap(messageMap);

      const nextSessions = loadSessionSummaries().filter((s) => s.id !== deleteThreadId);
      saveSessionSummaries(nextSessions);
      setSessions(nextSessions);

      // If deleting the active session, switch to a remaining one (or create a new empty session)
      if (deleteThreadId === threadId) {
        const nextThreadId = nextSessions[0]?.id ?? crypto.randomUUID();
        localStorage.setItem(CURRENT_THREAD_STORAGE_KEY, nextThreadId);

        if (!messageMap[nextThreadId]) {
          messageMap[nextThreadId] = [];
          saveMessageMap(messageMap);
          const ensured = upsertSessionSummary(loadSessionSummaries(), deriveSessionSummary(nextThreadId, []));
          saveSessionSummaries(ensured);
          setSessions(ensured);
        }

        setThreadId(nextThreadId);
        setMessages(messageMap[nextThreadId] ?? []);
        setStepLogs([]);
        setError(null);
        setPendingTool(null);
        setPendingChoices(null);
        setIsLoading(false);
        setRunStatus("idle");
        setStatusMessage("会话已删除，已切换到其他会话");
        setEffectiveModel(null);
      } else {
        setStatusMessage("会话已删除");
      }
    },
    [threadId],
  );

  const switchSession = useCallback((nextThreadId: string) => {
    abortRef.current?.abort();
    if (typeof window !== "undefined") {
      localStorage.setItem(CURRENT_THREAD_STORAGE_KEY, nextThreadId);
      const messageMap = loadMessageMap();
      setMessages(messageMap[nextThreadId] ?? []);
    }
    setThreadId(nextThreadId);
    setStepLogs([]);
    setError(null);
    setPendingTool(null);
    setPendingChoices(null);
    setIsLoading(false);
    setRunStatus("idle");
    setStatusMessage("已切换会话");
    setEffectiveModel(null);
  }, []);

  const approveTool = useCallback(
    async (approved: boolean) => {
      if (!pendingTool) return;
      const res = await fetch(aguiRequestPath("/api/approve-tool"), {
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
        setRunStatus("error");
        setStatusMessage("工具确认失败");
      } else {
        setPendingTool(null);
        setRunStatus(approved ? "running" : "completed");
        setStatusMessage(approved ? `已授权 ${pendingTool.toolName}，继续执行` : `已拒绝 ${pendingTool.toolName}`);
      }
    },
    [pendingTool],
  );

  const sendMessage = useCallback(
    async (text: string, modelName?: string) => {
      const trimmed = text.trim();
      if (!trimmed || !threadId || isLoading) return;

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      setError(null);
      setPendingTool(null);
      setPendingChoices(null);
      setIsLoading(true);
      setRunStatus("running");
      setStatusMessage("Nanobot 正在生成回复");

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
      let streamError = false;
      let sawRunFinished = false;
      // Declared outside try so the catch block can access it for diagnostics
      let lastFragment = "";

      try {
        const res = await fetch(aguiRequestPath("/api/chat"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: ac.signal,
          body: JSON.stringify({
            threadId,
            runId,
            messages: bodyMessages,
            humanInTheLoop: false,
            model_name: modelName?.trim() ? modelName.trim() : undefined,
          }),
        });

        if (res.status === 409) {
          setError("该会话已有请求进行中");
          setRunStatus("error");
          setStatusMessage("当前会话已有运行中的请求");
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
          setRunStatus("error");
          setStatusMessage("请求发送失败");
          rollbackNewTurn();
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          setError("无响应流");
          setRunStatus("error");
          setStatusMessage("未收到可读响应流");
          rollbackNewTurn();
          return;
        }

      const decoder = new TextDecoder();
      let buffer = "";
      // Accumulate file paths found in tool step logs during this run
      const toolArtifactPaths: string[] = [];

      const handleRec = (event: string, data: Record<string, unknown>) => {
        if (event === "RunStarted") {
            if (typeof data.model === "string" && data.model.trim()) {
              setEffectiveModel(data.model);
            }
          } else if (event === "TextMessageContent" && typeof data.delta === "string") {
            const d = data.delta;
            setMessages((prev) =>
              prev.map((m) => (m.id === asstId ? { ...m, content: m.content + d } : m)),
            );
          } else if (event === "StepStarted" && typeof data.text === "string") {
            const stepName = data.stepName === "tool" ? "tool" : "thinking";
            const stepText = String(data.text);
            setStepLogs((prev) => [...prev, { id: newId(), stepName, text: stepText }]);
            if (stepName === "tool") {
              // Extract any file paths embedded in the tool execution code
              const paths = extractPathsFromToolText(stepText);
              for (const p of paths) {
                if (!toolArtifactPaths.includes(p)) toolArtifactPaths.push(p);
              }
            }
            setRunStatus("running");
            setStatusMessage(stepName === "tool" ? "正在调用工具" : "正在分析问题");
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
            setRunStatus("awaitingApproval");
            setStatusMessage(`等待你确认：${String(data.toolName ?? "工具调用")}`);
          } else if (event === "RunFinished") {
            sawRunFinished = true;
            // Persist tool-inferred file paths into the assistant message
            if (toolArtifactPaths.length > 0) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId
                    ? {
                        ...m,
                        artifacts: [
                          ...new Set([...(m.artifacts ?? []), ...toolArtifactPaths]),
                        ],
                      }
                    : m,
                ),
              );
            }
            if (Array.isArray(data.choices)) {
              setPendingChoices(data.choices as ChoiceItem[]);
            }
            if (data.error && typeof data.error === "object" && data.error !== null) {
              const err = data.error as { code?: string; message?: string };
              setError(err.message ?? err.code ?? "Unknown error");
              setRunStatus("error");
              setStatusMessage(err.message ?? "本轮执行失败");
            } else {
              setRunStatus("completed");
              setStatusMessage(Array.isArray(data.choices) && data.choices.length > 0 ? "已生成下一步选项" : "本轮执行完成");
            }
          } else if (event === "Error") {
            if (typeof data.message === "string") {
              setError(data.message);
              setRunStatus("error");
              setStatusMessage(data.message);
            }
          }
        };

        try {
          while (true) {
            let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
            const timeoutPromise = new Promise<never>((_, reject) => {
              timeoutHandle = setTimeout(() => reject(new Error("SSE stream idle timeout")), STREAM_IDLE_TIMEOUT_MS);
            });
            let readResult: ReadableStreamReadResult<Uint8Array>;
            try {
              readResult = await Promise.race([reader.read(), timeoutPromise]);
            } finally {
              if (timeoutHandle) clearTimeout(timeoutHandle);
            }
            const { done, value } = readResult;
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            // Keep a rolling snapshot of the last 500 chars for diagnostics
            lastFragment = (lastFragment + chunk).slice(-500);
            buffer = applySseBlocks(buffer, (rec) => handleRec(rec.event, rec.data));
          }
          if (buffer.trim()) {
            const rec = parseSseRecord(buffer);
            if (rec) handleRec(rec.event, rec.data);
          }
        } finally {
          try {
            await reader.cancel();
          } catch {
            // ignore reader cancellation errors
          }
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          setRunStatus("idle");
          setStatusMessage("请求已取消");
          return;
        }
        streamError = true;
        console.error(
          "[useAgentChat] 流异常结束 —— 断流前最后收到的片段:",
          lastFragment || "(空，连接可能在首包前断开)",
          "\n原始错误:",
          e,
        );
        setError(e instanceof Error ? e.message : String(e));
        setRunStatus("error");
        setStatusMessage("本轮执行被中断");
        rollbackNewTurn();
      } finally {
        if (
          !sawRunFinished &&
          (runStatusRef.current === "running" || runStatusRef.current === "awaitingApproval")
        ) {
          setRunStatus(streamError ? "error" : "completed");
          setStatusMessage(streamError ? "流异常结束（兜底）" : "流已结束（兜底完成）");
        }
        setIsLoading(false);
      }
    },
    [threadId, isLoading, messages],
  );

  return {
    threadId,
    sessions,
    messages,
    stepLogs,
    isLoading,
    error,
    pendingTool,
    pendingChoices,
    runStatus,
    statusMessage,
    effectiveModel,
    sendMessage,
    approveTool,
    clearPendingChoices,
    clearChat,
    deleteMessage,
    deleteSession,
    createSession,
    switchSession,
  };
}
