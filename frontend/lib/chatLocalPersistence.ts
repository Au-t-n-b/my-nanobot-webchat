import { chatStorageScopeFromParts, sanitizeStorageSegment } from "@/lib/workbenchStorageKeys";

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
