"use client";

import { startTransition, useCallback, useEffect, useRef, useState } from "react";
import { getLocalStorage, safeRemoveItem, safeSetItem } from "@/lib/browserStorage";
import {
  getScopedChatKeys,
  LEGACY_CHAT,
  maybeMigrateChatFromLegacy,
  maybeMigrateLegacyChatCardBlob,
} from "@/lib/chatLocalPersistence";
import { applyTaskStatusSnapshot } from "@/lib/projectOverviewStore";
import { getWorkbenchChatStorageScope } from "@/lib/workbenchStorageScope";
import { WORKBENCH_SCOPE_CHANGED_EVENT } from "@/lib/workbenchStorageKeys";
import { parseSduiDocument } from "@/lib/sdui";
import type { SduiNode, SduiPatch, SduiUploadedFileRecord, SkillUiBootstrapEvent } from "@/lib/sdui";

export type { SkillUiBootstrapEvent };

const MESSAGES_CAP = 50;
const MESSAGES_MAX_BYTES = 1.8 * 1024 * 1024;
const STREAM_IDLE_TIMEOUT_MS = 90_000;   // 90 s — SSE proxy may buffer; heartbeat fires every 10 s

export type ChatCardAttachment = {
  cardId: string;
  docId: string;
  title?: string | null;
  node: SduiNode;
};

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Unix ms — UI 展示发送/完成时间（旧会话可能缺省） */
  createdAt?: number;
  /** File paths inferred from tool-execution step logs during this message's run */
  artifacts?: string[];
  kind?: "text" | "chat_card";
  chatCard?: ChatCardAttachment;
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

export type TaskStatusPayload = {
  updatedAt: string | number | null;
  overall: { doneCount: number; totalCount: number };
  summary?: {
    activeCount: number;
    pendingCount: number;
    completedCount: number;
    completionRate: number;
  };
  modules: Array<{
    id: string;
    name: string;
    status: "pending" | "running" | "completed" | "failed" | "skipped";
    steps: Array<{ id: string; name: string; done: boolean }>;
  }>;
};

/** SSE ``SkillAgentTaskResult`` — 预览洞察等子任务结构化回包（不落 SDUI 树） */
export type SkillAgentTaskResultEvent = {
  taskId: string;
  ok: boolean;
  report: Record<string, unknown> | null;
  error: string | null;
};

export type SkillUiDataPatchEvent = {
  id: string;
  /** 与目标面板 skill-ui URL 完全一致；缺省或非法载荷不会进入此事件 */
  syntheticPath: string;
  patch: SduiPatch;
  receivedAt: number;
};

function debugSkillUiPatchIngest(reason: string, detail: unknown) {
  if (typeof window === "undefined") return;
  const w = window as unknown as { __NANOBOT_DEBUG_SKILL_UI_PATCH__?: boolean };
  if (process.env.NODE_ENV !== "development" && !w.__NANOBOT_DEBUG_SKILL_UI_PATCH__) return;
  console.debug(`[SkillUiDataPatch] SSE ignored: ${reason}`, detail);
}

function sanitizeMessages(msgs: AgentMessage[]): AgentMessage[] {
  let toSave = msgs
    .filter((m) => {
      if (!m || typeof m.id !== "string" || (m.role !== "user" && m.role !== "assistant")) return false;
      if (m.kind === "chat_card") {
        return Boolean(m.chatCard && typeof m.chatCard.cardId === "string" && typeof m.chatCard.docId === "string");
      }
      return typeof m.content === "string";
    })
    .slice(-MESSAGES_CAP);
  let serialized = JSON.stringify(toSave);
  while (serialized.length > MESSAGES_MAX_BYTES && toSave.length > 1) {
    toSave = toSave.slice(1);
    serialized = JSON.stringify(toSave);
  }
  return toSave;
}

function loadMessageMap(scope: string): Record<string, AgentMessage[]> {
  if (typeof window === "undefined") return {};
  const ls = getLocalStorage();
  if (!ls) return {};
  maybeMigrateChatFromLegacy(ls, scope);
  try {
    const raw = ls.getItem(getScopedChatKeys(scope).messagesByThread);
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
  const ls = getLocalStorage();
  if (!ls) return [];
  try {
    const raw = ls.getItem(LEGACY_CHAT.legacyMessages);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? sanitizeMessages(parsed as AgentMessage[]) : [];
  } catch {
    return [];
  }
}

function saveMessageMap(map: Record<string, AgentMessage[]>, scope: string) {
  const ls = getLocalStorage();
  if (!ls) return;
  const sanitized = Object.fromEntries(
    Object.entries(map).map(([threadId, msgs]) => [threadId, sanitizeMessages(msgs)]),
  );
  safeSetItem(ls, getScopedChatKeys(scope).messagesByThread, JSON.stringify(sanitized));
}

function clipText(text: string, max: number): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max - 1)}…` : normalized;
}

function deriveSessionSummary(
  threadId: string,
  messages: AgentMessage[],
  prevSummary?: SessionSummary | null,
): SessionSummary {
  const firstUser = messages.find((m) => m.role === "user" && m.content.trim());
  const lastMessage = [...messages].reverse().find((m) => m.content.trim() || m.kind === "chat_card");
  const titleSource = firstUser?.content || lastMessage?.content || "新对话";
  const preview =
    lastMessage?.kind === "chat_card"
      ? clipText(lastMessage.chatCard?.title || "交互卡片", 42)
      : lastMessage
        ? clipText(lastMessage.content, 42)
        : "还没有消息";
  const fromMessages = messages.reduce((acc, m) => Math.max(acc, m.createdAt ?? 0), 0);
  const updatedAt = fromMessages > 0 ? fromMessages : prevSummary?.updatedAt ?? Date.now();
  return {
    id: threadId,
    title: clipText(titleSource, 24),
    preview,
    updatedAt,
    messageCount: messages.length,
  };
}

function loadSessionSummaries(scope: string): SessionSummary[] {
  if (typeof window === "undefined") return [];
  const ls = getLocalStorage();
  if (!ls) return [];
  maybeMigrateChatFromLegacy(ls, scope);
  try {
    const raw = ls.getItem(getScopedChatKeys(scope).sessions);
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

function saveSessionSummaries(summaries: SessionSummary[], scope: string) {
  const ls = getLocalStorage();
  if (!ls) return;
  safeSetItem(
    ls,
    getScopedChatKeys(scope).sessions,
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
// Skill-project relative paths written in tool step logs: Output/xxx.xlsx, RunTime/xxx
const _REL_PATH_RE = new RegExp(`(?:^|[\\s(["'])((Output|RunTime|Input|output|runtime|input)[/\\\\][^\\s\`\\]\\)"'\\n]{2,}\\.(?:${_FILE_EXT}))`, "gi");

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
  _REL_PATH_RE.lastIndex = 0;
  while ((m = _REL_PATH_RE.exec(text)) !== null) tryAdd(m[1] ?? "");
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
  // Some environments (older browsers / non-secure contexts) may not support crypto.randomUUID.
  // Always provide a stable fallback to avoid client runtime crashes.
  const c = (globalThis as unknown as { crypto?: Crypto }).crypto;
  if (c && typeof (c as any).randomUUID === "function") return (c as any).randomUUID();
  return `id_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function buildPresentChoicesChatCard(args: {
  threadId: string;
  runId: string;
  choices: ChoiceItem[];
}): AgentMessage {
  const tid = (args.threadId || "").trim() || "unknown";
  const rid = (args.runId || "").trim() || newId();
  const cardId = `present_choices:${tid}:${rid}`;
  return {
    id: newId(),
    role: "assistant",
    content: "",
    kind: "chat_card",
    chatCard: {
      cardId,
      docId: `chat:${tid}`,
      title: "需要你的输入 · 选项确认",
      node: {
        type: "ChoiceCard",
        id: `choice-${cardId}`,
        title: "请选择下一步操作",
        options: args.choices.map((c) => ({ id: c.value, label: c.label })),
      },
    },
  } satisfies AgentMessage;
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
  const [scopeEpoch, setScopeEpoch] = useState(0);
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
  /** 连续多条 SkillUiDataPatch：单 state 会互相覆盖，导致 Stepper 等早期 patch 丢失；用队列逐条应用。 */
  const [skillUiPatchQueue, setSkillUiPatchQueue] = useState<SkillUiDataPatchEvent[]>([]);
  const [skillUiBootstrapEvent, setSkillUiBootstrapEvent] = useState<SkillUiBootstrapEvent | null>(null);
  const [taskStatusEvent, setTaskStatusEvent] = useState<TaskStatusPayload | null>(null);
  /** 工具级模块焦点：仅由 SSE ModuleSessionFocus 维护，不用 Patch 超时猜测 */
  const [activeModuleIds, setActiveModuleIds] = useState<ReadonlySet<string>>(() => new Set());
  const abortRef = useRef<AbortController | null>(null);
  const hydratedRef = useRef(false);
  const runStatusRef = useRef<RunStatus>("idle");
  /** 清空会话前快照，供 Toast「撤销」恢复（仅内存 + localStorage 会话条） */
  const clearChatUndoRef = useRef<{
    messages: AgentMessage[];
    stepLogs: StepLog[];
    pendingTool: ToolPendingPayload | null;
    pendingChoices: ChoiceItem[] | null;
    runStatus: RunStatus;
    statusMessage: string;
    effectiveModel: string | null;
  } | null>(null);
  /** Latest messages for sendMessage body — avoids putting `messages` in sendMessage deps (streaming updates would recreate the callback every token and can amplify nested re-renders). */
  const messagesRef = useRef<AgentMessage[]>([]);
  const skillAgentTaskResultListenersRef = useRef(new Set<(p: SkillAgentTaskResultEvent) => void>());

  const subscribeSkillAgentTaskResult = useCallback((fn: (p: SkillAgentTaskResultEvent) => void) => {
    const s = skillAgentTaskResultListenersRef.current;
    s.add(fn);
    return () => {
      s.delete(fn);
    };
  }, []);

  useEffect(() => {
    runStatusRef.current = runStatus;
  }, [runStatus]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const bump = () => setScopeEpoch((n) => n + 1);
    window.addEventListener(WORKBENCH_SCOPE_CHANGED_EVENT, bump);
    window.addEventListener("storage", bump);
    return () => {
      window.removeEventListener(WORKBENCH_SCOPE_CHANGED_EVENT, bump);
      window.removeEventListener("storage", bump);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    abortRef.current?.abort();
    const scope = getWorkbenchChatStorageScope();
    const ls = getLocalStorage();
    if (!ls) return;
    maybeMigrateChatFromLegacy(ls, scope);
    const keys = getScopedChatKeys(scope);
    const messageMap = loadMessageMap(scope);
    let tid = ls.getItem(keys.currentThread) ?? null;
    const initialSessions = loadSessionSummaries(scope);
    if (!tid) tid = newId();
    if (!messageMap[tid]) {
      maybeMigrateLegacyChatCardBlob(ls, scope, tid);
      const legacy = loadLegacyMessages();
      if (legacy.length > 0) {
        messageMap[tid] = legacy;
        saveMessageMap(messageMap, scope);
        safeRemoveItem(ls, LEGACY_CHAT.legacyMessages);
      }
    }
    const prevS = initialSessions.find((s) => s.id === tid);
    const ensured = upsertSessionSummary(
      initialSessions,
      deriveSessionSummary(tid, messageMap[tid] ?? [], prevS),
    );
    safeSetItem(ls, keys.currentThread, tid);
    saveSessionSummaries(ensured, scope);
    setSessions(ensured);
    setThreadId(tid);
    setMessages(messageMap[tid] ?? []);
    setStepLogs([]);
    setError(null);
    setPendingTool(null);
    setPendingChoices(null);
    setIsLoading(false);
    setRunStatus("idle");
    setStatusMessage("准备就绪");
    setEffectiveModel(null);
    setSkillUiPatchQueue([]);
    setSkillUiBootstrapEvent(null);
    setTaskStatusEvent(null);
    setActiveModuleIds(new Set());
    hydratedRef.current = true;
  }, [scopeEpoch]);

  useEffect(() => {
    if (!hydratedRef.current || !threadId) return;
    // Persisting + updating session list on every token can create extremely
    // deep update chains in React dev/fast-refresh scenarios. Debounce to a
    // single update per small window.
    let cancelled = false;
    const handle = window.setTimeout(() => {
      if (cancelled) return;
      const scope = getWorkbenchChatStorageScope();
      const messageMap = loadMessageMap(scope);
      messageMap[threadId] = sanitizeMessages(messages);
      saveMessageMap(messageMap, scope);
      const summaries = loadSessionSummaries(scope);
      const prev = summaries.find((s) => s.id === threadId);
      const nextSessions = upsertSessionSummary(summaries, deriveSessionSummary(threadId, messages, prev));
      saveSessionSummaries(nextSessions, scope);
      setSessions(nextSessions);
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [messages, threadId, scopeEpoch]);

  const deleteMessage = useCallback(
    (id: string) => {
      setMessages((prev) => {
        const next = prev.filter((m) => m.id !== id);
        if (threadId) {
          const scope = getWorkbenchChatStorageScope();
          const messageMap = loadMessageMap(scope);
          messageMap[threadId] = sanitizeMessages(next);
          saveMessageMap(messageMap, scope);
          const summ = loadSessionSummaries(scope);
          const prevS = summ.find((s) => s.id === threadId);
          const nextSummaries = upsertSessionSummary(summ, deriveSessionSummary(threadId, next, prevS));
          saveSessionSummaries(nextSummaries, scope);
          setSessions(nextSummaries);
        }
        return next;
      });
    },
    [threadId],
  );

  const clearChat = useCallback(
    (opts?: { saveUndoSnapshot?: boolean }) => {
      if (opts?.saveUndoSnapshot && typeof structuredClone === "function") {
        try {
          clearChatUndoRef.current = {
            messages: structuredClone(messagesRef.current),
            stepLogs: structuredClone(stepLogs),
            pendingTool: pendingTool ? structuredClone(pendingTool) : null,
            pendingChoices: pendingChoices ? structuredClone(pendingChoices) : null,
            runStatus,
            statusMessage,
            effectiveModel,
          };
        } catch {
          clearChatUndoRef.current = null;
        }
      } else {
        clearChatUndoRef.current = null;
      }
      if (typeof window !== "undefined" && threadId) {
        const scope = getWorkbenchChatStorageScope();
        const messageMap = loadMessageMap(scope);
        messageMap[threadId] = [];
        saveMessageMap(messageMap, scope);
        const summ = loadSessionSummaries(scope);
        const prevS = summ.find((s) => s.id === threadId);
        const nextSessions = upsertSessionSummary(summ, deriveSessionSummary(threadId, [], prevS));
        saveSessionSummaries(nextSessions, scope);
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
      setSkillUiPatchQueue([]);
    },
    [threadId, stepLogs, pendingTool, pendingChoices, runStatus, statusMessage, effectiveModel],
  );

  const undoClearChat = useCallback(() => {
    const snap = clearChatUndoRef.current;
    if (!snap || !threadId) return false;
    clearChatUndoRef.current = null;
    setMessages(snap.messages);
    setStepLogs(snap.stepLogs);
    setPendingTool(snap.pendingTool);
    setPendingChoices(snap.pendingChoices);
    setRunStatus(snap.runStatus);
    setStatusMessage(snap.statusMessage);
    setEffectiveModel(snap.effectiveModel);
    if (typeof window !== "undefined") {
      const scope = getWorkbenchChatStorageScope();
      const messageMap = loadMessageMap(scope);
      messageMap[threadId] = sanitizeMessages(snap.messages);
      saveMessageMap(messageMap, scope);
      const summ = loadSessionSummaries(scope);
      const prevS = summ.find((s) => s.id === threadId);
      const nextSessions = upsertSessionSummary(summ, deriveSessionSummary(threadId, snap.messages, prevS));
      saveSessionSummaries(nextSessions, scope);
      setSessions(nextSessions);
    }
    return true;
  }, [threadId]);

  const clearPendingChoices = useCallback(() => {
    setPendingChoices(null);
  }, []);

  const lockPresentChoicesCard = useCallback((cardId: string, submittedValue: string) => {
    const cid = (cardId || "").trim();
    const v = (submittedValue || "").trim();
    if (!cid || !v) return;
    setMessages((prev) =>
      prev.map((m) => {
        if (m.kind !== "chat_card" || !m.chatCard || m.chatCard.cardId !== cid) return m;
        const node = m.chatCard.node as any;
        if (!node || typeof node !== "object" || node.type !== "ChoiceCard") return m;
        if (String(node.submittedValue ?? "").trim()) return m;
        return {
          ...m,
          chatCard: {
            ...m.chatCard,
            node: { ...node, submittedValue: v },
          },
        };
      }),
    );
  }, []);

  const lockFilePickerCard = useCallback((cardId: string, uploads: SduiUploadedFileRecord[]) => {
    const cid = (cardId || "").trim();
    const list = Array.isArray(uploads) ? uploads : [];
    if (!cid || list.length === 0) return;
    setMessages((prev) =>
      prev.map((m) => {
        if (m.kind !== "chat_card" || !m.chatCard || m.chatCard.cardId !== cid) return m;
        const node = m.chatCard.node as any;
        if (!node || typeof node !== "object" || node.type !== "FilePicker") return m;
        if (Boolean(node.submitted) && Array.isArray(node.uploads) && node.uploads.length) return m;
        return {
          ...m,
          chatCard: {
            ...m.chatCard,
            node: { ...node, submitted: true, uploads: list },
          },
        };
      }),
    );
  }, []);

  const createSession = useCallback(() => {
    abortRef.current?.abort();
    setActiveModuleIds(new Set());
    const nextThreadId = newId();
    if (typeof window !== "undefined") {
      const scope = getWorkbenchChatStorageScope();
      const keys = getScopedChatKeys(scope);
      const ls = getLocalStorage();
      if (ls) safeSetItem(ls, keys.currentThread, nextThreadId);
      const summ = loadSessionSummaries(scope);
      const prevNew = summ.find((s) => s.id === nextThreadId);
      const nextSessions = upsertSessionSummary(summ, deriveSessionSummary(nextThreadId, [], prevNew));
      saveSessionSummaries(nextSessions, scope);
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
    setSkillUiPatchQueue([]);
  }, []);

  const deleteSession = useCallback(
    (deleteThreadId: string) => {
      abortRef.current?.abort();
      if (typeof window === "undefined") return;

      const scope = getWorkbenchChatStorageScope();
      const messageMap = loadMessageMap(scope);
      delete messageMap[deleteThreadId];
      saveMessageMap(messageMap, scope);

      const nextSessions = loadSessionSummaries(scope).filter((s) => s.id !== deleteThreadId);
      saveSessionSummaries(nextSessions, scope);
      setSessions(nextSessions);

      // If deleting the active session, switch to a remaining one (or create a new empty session)
      if (deleteThreadId === threadId) {
        setActiveModuleIds(new Set());
        const nextThreadId = nextSessions[0]?.id ?? newId();
        const keys = getScopedChatKeys(scope);
        const ls = getLocalStorage();
        if (ls) safeSetItem(ls, keys.currentThread, nextThreadId);

        if (!messageMap[nextThreadId]) {
          messageMap[nextThreadId] = [];
          saveMessageMap(messageMap, scope);
          const summ = loadSessionSummaries(scope);
          const prevNew = summ.find((s) => s.id === nextThreadId);
          const ensured = upsertSessionSummary(summ, deriveSessionSummary(nextThreadId, [], prevNew));
          saveSessionSummaries(ensured, scope);
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
    setActiveModuleIds(new Set());
    if (typeof window !== "undefined") {
      const scope = getWorkbenchChatStorageScope();
      const keys = getScopedChatKeys(scope);
      const ls = getLocalStorage();
      if (ls) safeSetItem(ls, keys.currentThread, nextThreadId);
      const messageMap = loadMessageMap(scope);
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
    setSkillUiPatchQueue([]);
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

  const stopGenerating = useCallback(() => {
    // Best-effort cancel the active fetch/SSE stream.
    abortRef.current?.abort();
  }, []);

  const sendChatRequest = useCallback(
    async (
      text: string,
      modelName?: string,
      options?: {
        showInTranscript?: boolean;
        /** 与 `showInTranscript: false` 联用：不展示 user 气泡，但展示 assistant 流式/气泡（如冷启引导） */
        showAssistantInTranscript?: boolean;
        showCompletionMessage?: boolean;
      },
    ): Promise<boolean> => {
      const trimmed = text.trim();
      const showUserInTranscript = options?.showInTranscript !== false;
      const showAssistantInTranscript =
        showUserInTranscript || options?.showAssistantInTranscript === true;
      // Skill HITL 回传可能在「主对话 SSE 尚未结束」时发出；此时 isLoading 仍为 true。
      // 若在此处短路，用户点击「完成上传并继续」会被静默丢弃，技能永远不 resume。
      let bypassLoadingGuard = false;
      if (!showUserInTranscript && trimmed) {
        try {
          const j = JSON.parse(trimmed) as { type?: unknown; verb?: unknown };
          const verb = typeof j.verb === "string" ? j.verb.trim() : "";
          if (
            j &&
            typeof j === "object" &&
            j.type === "chat_card_intent" &&
            (verb === "skill_runtime_result" ||
              verb === "skill_runtime_resume" ||
              verb === "skill_runtime_event" ||
              verb === "skill_runtime_start")
          ) {
            bypassLoadingGuard = true;
          }
        } catch {
          // 非 JSON：保持默认（仍受 isLoading 约束）
        }
      }
      if (!trimmed || !threadId || (isLoading && !bypassLoadingGuard)) return false;
      const showCompletionMessage = options?.showCompletionMessage === true;

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      setError(null);
      setPendingTool(null);
      setPendingChoices(null);
      setIsLoading(true);
      setRunStatus("running");
      setStatusMessage("Nanobot 正在生成回复");

      const userId = showUserInTranscript ? newId() : "";
      const asstId = showAssistantInTranscript ? newId() : "";

      const bodyMessages = [
        ...messagesRef.current
          .filter((m) => m.kind !== "chat_card")
          .map((m) => ({ role: m.role, content: m.content })),
        { role: "user" as const, content: trimmed },
      ];

      if (showUserInTranscript) {
        setMessages((prev) => [
          ...prev,
          { id: userId, role: "user", content: trimmed },
          { id: asstId, role: "assistant", content: "" },
        ]);
      } else if (showAssistantInTranscript) {
        setMessages((prev) => [...prev, { id: asstId, role: "assistant", content: "" }]);
      }

      const runId = newId();

      const rollbackNewTurn = () => {
        if (!showUserInTranscript && !showAssistantInTranscript) return;
        setMessages((prev) => {
          if (showUserInTranscript) {
            return prev.filter((m) => m.id !== asstId && m.id !== userId);
          }
          if (asstId) {
            return prev.filter((m) => m.id !== asstId);
          }
          return prev;
        });
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
          return false;
        }

        if (!res.ok) {
          let msg = `HTTP ${res.status}`;
          try {
            const text = await res.text();
            try {
              const j = JSON.parse(text) as { detail?: string };
              if (j?.detail) msg = j.detail;
            } catch {
              if (text) msg = text;
            }
          } catch {
            // ignore body read errors
          }
          setError(msg);
          setRunStatus("error");
          setStatusMessage("请求发送失败");
          rollbackNewTurn();
          return false;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          setError("无响应流");
          setRunStatus("error");
          setStatusMessage("未收到可读响应流");
          rollbackNewTurn();
          return false;
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
            if (!showAssistantInTranscript) return;
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
            const finishMsg = typeof data.message === "string" ? data.message.trim() : "";
            // 仅当助手消息在 transcript 时写入 RunFinished.message。全静默（HITL）勿追加完成语，防幽灵气泡。
            const allowSilentCompletionMessage = !showCompletionMessage || !/^已进入下一步[:：]/.test(finishMsg);
            if (showAssistantInTranscript && finishMsg && allowSilentCompletionMessage) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId
                    ? { ...m, content: (m.content && m.content.trim()) ? m.content : finishMsg }
                    : m,
                ),
              );
            }
            // Persist tool-inferred file paths into the assistant message
            if (showAssistantInTranscript && toolArtifactPaths.length > 0) {
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
              const list = (data.choices as unknown[])
                .map((x) => ({
                  label: typeof (x as any)?.label === "string" ? String((x as any).label).trim() : "",
                  value: typeof (x as any)?.value === "string" ? String((x as any).value).trim() : "",
                }))
                .filter((x) => x.label && x.value);
              if (showAssistantInTranscript && list.length > 0) {
                const tid = typeof data.threadId === "string" ? data.threadId : threadId;
                const rid = typeof data.runId === "string" ? data.runId : newId();
                setMessages((prev) => [...prev, buildPresentChoicesChatCard({ threadId: tid || threadId, runId: rid, choices: list })]);
                setPendingChoices(null);
              } else {
                setPendingChoices(list.length > 0 ? list : null);
              }
            }
            if (data.error && typeof data.error === "object" && data.error !== null) {
              const err = data.error as { code?: string; message?: string };
              setError(err.message ?? err.code ?? "Unknown error");
              setRunStatus("error");
              setStatusMessage(err.message ?? "本轮执行失败");
            } else {
              setRunStatus("completed");
              setStatusMessage(
                Array.isArray(data.choices) && data.choices.length > 0 ? "已生成下一步选项" : "就绪",
              );
            }
          } else if (event === "Error") {
            if (typeof data.message === "string") {
              setError(data.message);
              setRunStatus("error");
              setStatusMessage(data.message);
            }
          } else if (event === "Heartbeat") {
            // Backend keepalive — update status bar so the user knows the
            // agent is alive; do NOT add a step log entry (would be noisy).
            const msg = typeof data.message === "string" ? data.message : "Agent 正在处理中…";
            setStatusMessage(msg);
          } else if (event === "ModuleSessionFocus") {
            const evtTid = String(data.threadId ?? "").trim();
            if (evtTid && evtTid !== threadId) return;
            const mid = String(data.moduleId ?? "").trim();
            const st = String(data.status ?? "").trim();
            if (!mid || (st !== "running" && st !== "idle")) return;
            startTransition(() => {
              setActiveModuleIds((prev) => {
                const next = new Set(prev);
                if (st === "running") next.add(mid);
                else next.delete(mid);
                return next;
              });
            });
          } else if (event === "TaskStatusUpdate") {
            const modules = data.modules;
            const overall = data.overall;
            if (!Array.isArray(modules) || !overall || typeof overall !== "object") return;
            startTransition(() => {
              const snapshot = data as unknown as TaskStatusPayload;
              applyTaskStatusSnapshot(snapshot);
              setTaskStatusEvent(snapshot);
            });
          } else if (event === "SkillAgentTaskResult") {
            const evtThread = typeof data.threadId === "string" ? data.threadId.trim() : "";
            if (evtThread && evtThread !== threadId) return;
            const taskId = typeof data.taskId === "string" ? data.taskId.trim() : "";
            const payload: SkillAgentTaskResultEvent = {
              taskId,
              ok: data.ok === true,
              report: data.report !== null && typeof data.report === "object" ? (data.report as Record<string, unknown>) : null,
              error: typeof data.error === "string" && data.error.trim() ? data.error.trim() : null,
            };
            const listeners = skillAgentTaskResultListenersRef.current;
            if (!listeners.size) return;
            startTransition(() => {
              listeners.forEach((fn) => {
                try {
                  fn(payload);
                } catch {
                  // ignore subscriber errors
                }
              });
            });
          } else if (event === "SkillUiBootstrap") {
            const syntheticPathRaw = typeof data.syntheticPath === "string" ? data.syntheticPath.trim() : "";
            if (!syntheticPathRaw) return;
            const parsed = parseSduiDocument(data.document);
            if (!parsed.ok) return;
            startTransition(() => {
              setSkillUiBootstrapEvent({
                id: newId(),
                syntheticPath: syntheticPathRaw,
                document: parsed.doc,
                receivedAt: Date.now(),
              });
            });
          } else if (event === "SkillUiDataPatch") {
            // v3 生产契约：syntheticPath 必填；patch 含 docId、revision（整数）。
            const syntheticPathRaw = typeof data.syntheticPath === "string" ? data.syntheticPath.trim() : "";
            if (!syntheticPathRaw) {
              debugSkillUiPatchIngest("missing syntheticPath", data);
              return;
            }
            const rawPatch = (data.patch ?? data) as unknown;
            const patchObj = rawPatch as Partial<SduiPatch> | null;
            if (!patchObj || typeof patchObj !== "object") {
              debugSkillUiPatchIngest("patch not an object", data);
              return;
            }
            if (patchObj.schemaVersion !== 3 || patchObj.type !== "SduiPatch" || !Array.isArray(patchObj.ops)) {
              debugSkillUiPatchIngest("not a v3 SduiPatch", {
                schemaVersion: patchObj.schemaVersion,
                type: patchObj.type,
                hasOps: Array.isArray(patchObj.ops),
              });
              return;
            }
            const docId = typeof patchObj.docId === "string" ? patchObj.docId.trim() : "";
            if (!docId) {
              debugSkillUiPatchIngest("missing docId", data);
              return;
            }
            const rev = patchObj.revision;
            if (typeof rev !== "number" || !Number.isFinite(rev)) {
              debugSkillUiPatchIngest("missing or invalid revision", { docId, revision: patchObj.revision });
              return;
            }
            startTransition(() => {
              const evt: SkillUiDataPatchEvent = {
                id: newId(),
                syntheticPath: syntheticPathRaw,
                patch: patchObj as SduiPatch,
                receivedAt: Date.now(),
              };
              setSkillUiPatchQueue((prev) => {
                const next = [...prev, evt];
                return next.length > 512 ? next.slice(-512) : next;
              });
            });
          } else if (event === "SkillUiChatCard") {
            const cardId = typeof data.cardId === "string" ? data.cardId.trim() : "";
            const docIdRaw = typeof data.docId === "string" ? data.docId.trim() : "";
            if (!cardId) return;
            const docId = docIdRaw || `chat:${String(data.threadId ?? "").trim() || "unknown"}`;
            const mode = data.mode === "replace" ? "replace" : "append";
            const title = typeof data.title === "string" ? data.title : null;
            const rawNode = (data.node ?? data.document) as unknown;
            const node = (rawNode && typeof rawNode === "object" ? rawNode : { type: "Text", content: "（空卡片）" }) as SduiNode;
            const n = node as { type?: string; context?: unknown; actions?: unknown[] };
            const actions = Array.isArray(n.actions) ? n.actions : [];
            const isPlainGuidance = n.type === "GuidanceCard" && actions.length === 0;
            const guidanceText = isPlainGuidance ? String(n.context ?? "").trim() : "";

            if (isPlainGuidance) {
              const stableId = `guidance-bubble:${cardId}`;
              startTransition(() => {
                setMessages((prev) => {
                  const idxCard = prev.findIndex((m) => m.kind === "chat_card" && m.chatCard?.cardId === cardId);
                  const idxBubble = prev.findIndex((m) => m.id === stableId);
                  if (!guidanceText) {
                    if (idxBubble >= 0) {
                      const next = [...prev];
                      next.splice(idxBubble, 1);
                      return next;
                    }
                    if (idxCard >= 0) {
                      const next = [...prev];
                      next.splice(idxCard, 1);
                      return next;
                    }
                    return prev;
                  }
                  if (idxBubble >= 0) {
                    const next = [...prev];
                    next[idxBubble] = { ...next[idxBubble], content: guidanceText, kind: undefined, chatCard: undefined };
                    return next;
                  }
                  if (idxCard >= 0) {
                    const next = [...prev];
                    next[idxCard] = {
                      id: stableId,
                      role: "assistant",
                      content: guidanceText,
                    };
                    return next;
                  }
                  return [
                    ...prev,
                    {
                      id: stableId,
                      role: "assistant" as const,
                      content: guidanceText,
                    },
                  ];
                });
              });
              return;
            }

            startTransition(() => {
              setMessages((prev) => {
                if (mode === "replace") {
                  const idx = prev.findIndex((m) => m.kind === "chat_card" && m.chatCard?.cardId === cardId);
                  if (idx >= 0) {
                    const next = [...prev];
                    next[idx] = {
                      ...next[idx],
                      content: "",
                      kind: "chat_card",
                      chatCard: { cardId, docId, title, node },
                    };
                    return next;
                  }
                  const stableGuidance = `guidance-bubble:${cardId}`;
                  const idxG = prev.findIndex((m) => m.id === stableGuidance);
                  if (idxG >= 0) {
                    const next = [...prev];
                    next[idxG] = {
                      id: newId(),
                      role: "assistant",
                      content: "",
                      kind: "chat_card",
                      chatCard: { cardId, docId, title, node },
                    };
                    return next;
                  }
                }
                return [
                  ...prev,
                  {
                    id: newId(),
                    role: "assistant" as const,
                    content: "",
                    kind: "chat_card" as const,
                    chatCard: { cardId, docId, title, node },
                  },
                ];
              });
            });
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
        return !streamError;
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          // User-initiated cancel — keep partial assistant content, do not treat as error.
          setRunStatus("idle");
          setStatusMessage("已停止生成");
          return false;
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
        return false;
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
    [threadId, isLoading],
  );

  const sendMessage = useCallback(
    async (text: string, modelName?: string) => {
      await sendChatRequest(text, modelName, { showInTranscript: true });
    },
    [sendChatRequest],
  );

  const sendSilentMessage = useCallback(
    async (text: string, modelName?: string) => {
      await sendChatRequest(text, modelName, { showInTranscript: false, showCompletionMessage: true });
    },
    [sendChatRequest],
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
    skillUiPatchQueue,
    /** 兼容仅关心「最后一条」的组件（如路由 syntheticPath） */
    skillUiPatchEvent: skillUiPatchQueue.at(-1) ?? null,
    skillUiBootstrapEvent,
    /** 最近一次 TaskStatusUpdate；混合子任务模块 id 形如 `hybrid:{skillName}`（见 hybridSubtaskHintFromTaskStatus） */
    taskStatusEvent,
    activeModuleIds,
    /** 订阅 ``SkillAgentTaskResult`` SSE（预览洞察等）；返回取消订阅函数 */
    subscribeSkillAgentTaskResult,
    sendMessage,
    sendSilentMessage,
    /** 与 sendSilentMessage 相同请求体，但返回 `true` 表示流式轮次正常结束；冷启动/需判成功时用 */
    sendChatRequest,
    stopGenerating,
    approveTool,
    clearPendingChoices,
    lockPresentChoicesCard,
    lockFilePickerCard,
    clearChat,
    undoClearChat,
    deleteMessage,
    deleteSession,
    createSession,
    switchSession,
  };
}
