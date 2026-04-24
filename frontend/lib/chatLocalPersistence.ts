import { chatStorageScopeFromParts, sanitizeStorageSegment } from "@/lib/workbenchStorageKeys";

const TRASH_30D_MS = 30 * 24 * 60 * 60 * 1000;
const TRASH_MAX = 5;

/** 用户清空当前会话时写入的回收项（同 scope 最多 5 条、30 天自动失效） */
export type TrashedSessionV1 = {
  sessionId: string;
  title: string;
  trashedAt: number;
  /** 便于 UI 显示 */
  messageCount: number;
  /** 已序列化的消息列表（同 thread 的 AgentMessage[] JSON） */
  messagesJson: string;
};

function trashStorageKey(scope: string): string {
  return `trashed_sessions_v1::${sanitizeStorageSegment(scope)}`;
}

function nowTrimTrash(entries: TrashedSessionV1[]): TrashedSessionV1[] {
  const t = Date.now();
  return entries
    .filter((e) => t - e.trashedAt < TRASH_30D_MS)
    .slice(0, TRASH_MAX);
}

export function readTrashedSessions(ls: Storage, scope: string): TrashedSessionV1[] {
  try {
    const raw = ls.getItem(trashStorageKey(scope));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return nowTrimTrash(parsed as TrashedSessionV1[]);
  } catch {
    return [];
  }
}

export function recordClearedThreadToTrash(
  ls: Storage,
  scope: string,
  payload: { sessionId: string; title: string; messages: unknown[] },
): void {
  if (!payload.sessionId) return;
  const prev = readTrashedSessions(ls, scope);
  const messagesJson = JSON.stringify(payload.messages ?? []);
  const next: TrashedSessionV1[] = nowTrimTrash([
    {
      sessionId: payload.sessionId,
      title: payload.title || "会话",
      trashedAt: Date.now(),
      messageCount: payload.messages.length,
      messagesJson,
    },
    ...prev.filter((e) => e.sessionId !== payload.sessionId),
  ]);
  ls.setItem(trashStorageKey(scope), JSON.stringify(next.slice(0, TRASH_MAX)));
}

export function removeTrashedSession(ls: Storage, scope: string, sessionId: string, trashedAt: number): void {
  const prev = readTrashedSessions(ls, scope);
  const next = prev.filter((e) => !(e.sessionId === sessionId && e.trashedAt === trashedAt));
  if (next.length === 0) {
    ls.removeItem(trashStorageKey(scope));
  } else {
    ls.setItem(trashStorageKey(scope), JSON.stringify(next));
  }
}

export function parseTrashedMessages(entry: TrashedSessionV1): unknown[] {
  try {
    const p = JSON.parse(entry.messagesJson) as unknown;
    return Array.isArray(p) ? p : [];
  } catch {
    return [];
  }
}

/** 升级前全局唯一 key（与 useAgentChat 历史一致） */
export const LEGACY_CHAT = {
  currentThread: "nanobot_agui_current_thread_id",
  messagesByThread: "nanobot_agui_messages_by_thread",
  sessions: "nanobot_agui_sessions",
  legacyMessages: "nanobot_agui_messages",
} as const;

export function getScopedChatKeys(scope: string): {
  currentThread: string;
  messagesByThread: string;
  sessions: string;
} {
  const safe = sanitizeStorageSegment(scope);
  return {
    currentThread: `${LEGACY_CHAT.currentThread}::${safe}`,
    messagesByThread: `${LEGACY_CHAT.messagesByThread}::${safe}`,
    sessions: `${LEGACY_CHAT.sessions}::${safe}`,
  };
}

/** 仅将「旧版未分区」数据迁到访客默认命名空间，避免覆盖已登录用户分区 */
export function isGuestDefaultLegacyScope(scope: string): boolean {
  return scope === chatStorageScopeFromParts("_guest", "");
}

/**
 * 首次使用 `_guest` + 未选项目 的命名空间时，从未分区 legacy 拷贝一次，保持老用户数据可见。
 */
export function maybeMigrateChatFromLegacy(ls: Storage, scope: string): void {
  if (!isGuestDefaultLegacyScope(scope)) return;
  const sk = getScopedChatKeys(scope);
  if (ls.getItem(sk.messagesByThread)) return;
  const leg = ls.getItem(LEGACY_CHAT.messagesByThread);
  if (!leg) return;
  ls.setItem(sk.messagesByThread, leg);
  const ct = ls.getItem(LEGACY_CHAT.currentThread);
  if (ct) ls.setItem(sk.currentThread, ct);
  const sess = ls.getItem(LEGACY_CHAT.sessions);
  if (sess) ls.setItem(sk.sessions, sess);
}

export function maybeMigrateLegacyChatCardBlob(ls: Storage, scope: string, tid: string): void {
  if (!isGuestDefaultLegacyScope(scope)) return;
  const sk = getScopedChatKeys(scope);
  const leg = ls.getItem(LEGACY_CHAT.legacyMessages);
  if (!leg) return;
  try {
    const messageMapRaw = ls.getItem(sk.messagesByThread);
    const messageMap: Record<string, unknown> = messageMapRaw
      ? (JSON.parse(messageMapRaw) as Record<string, unknown>)
      : {};
    if (messageMap[tid]) return;
    const arr = JSON.parse(leg) as unknown;
    if (Array.isArray(arr)) {
      messageMap[tid] = arr;
      ls.setItem(sk.messagesByThread, JSON.stringify(messageMap));
    }
    ls.removeItem(LEGACY_CHAT.legacyMessages);
  } catch {
    /* ignore */
  }
}
