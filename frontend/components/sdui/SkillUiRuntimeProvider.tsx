"use client";

/**
 * SDUI 运行时：Button / FilePicker 等通过 `postToAgent` / `postToAgentSilently` 回传 JSON intent。
 * Skill-First 混合模式下的受控子任务由 **driver → stdout → bridge** 触发，不经过本层；
 * 但若将来需要由卡片触发 `skill_runtime_event`，仍应复用上述静默通道以保持行为一致。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { expandInputPlaceholders } from "@/lib/sdui";
import type { SduiUploadedFileRecord } from "@/lib/sdui";
import { useProjectOverviewStore } from "@/lib/projectOverviewStore";

type SyncBehavior = "debounce" | "immediate";

type SyncRequest = {
  docId: string;
  key: string;
  value: unknown;
};

type SyncStateSender = (req: SyncRequest) => Promise<{ ok: true; revision?: number } | { ok: false }>;

function makeDefaultSyncSender(): SyncStateSender {
  return async (req) => {
    try {
      const res = await fetch("/api/skill/state/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docId: req.docId, key: req.key, value: req.value }),
      });
      const json = (await res.json().catch(() => ({}))) as { revision?: unknown };
      if (!res.ok) return { ok: false };
      const rev = typeof json.revision === "number" && Number.isFinite(json.revision) ? json.revision : undefined;
      return { ok: true, revision: rev };
    } catch {
      return { ok: false };
    }
  };
}

function trySendBeacon(req: SyncRequest): boolean {
  try {
    if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") return false;
    const body = JSON.stringify({ docId: req.docId, key: req.key, value: req.value });
    const blob = new Blob([body], { type: "application/json" });
    return navigator.sendBeacon("/api/skill/state/sync", blob);
  } catch {
    return false;
  }
}

async function flushViaFetchKeepalive(req: SyncRequest): Promise<void> {
  try {
    await fetch("/api/skill/state/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ docId: req.docId, key: req.key, value: req.value }),
      keepalive: true,
    });
  } catch {
    // best-effort
  }
}

export function useSyncState(args: {
  getDocId: () => string;
  sender?: SyncStateSender;
  debounceMs?: number;
  onAckRevision?: (revision: number) => void;
}) {
  const senderRef = useRef<SyncStateSender>(args.sender ?? makeDefaultSyncSender());
  const getDocIdRef = useRef(args.getDocId);
  const onAckRevisionRef = useRef(args.onAckRevision);
  const debounceMs = args.debounceMs ?? 250;

  // Keep latest callbacks without forcing hook recomputation.
  useEffect(() => {
    getDocIdRef.current = args.getDocId;
    onAckRevisionRef.current = args.onAckRevision;
    if (args.sender) senderRef.current = args.sender;
  }, [args.getDocId, args.onAckRevision, args.sender]);
  const pendingRef = useRef<
    Map<
      string,
      {
        timer: number | null;
        value: unknown;
        lastQueuedAt: number;
      }
    >
  >(new Map());

  const flushKey = useCallback(
    async (key: string, value: unknown) => {
      const docId = getDocIdRef.current().trim();
      if (!docId || !key.trim()) return;
      const req: SyncRequest = { docId, key, value };
      const ok = trySendBeacon(req);
      if (ok) return;
      await flushViaFetchKeepalive(req);
    },
    [],
  );

  const syncState = useCallback(
    (p: { key: string; value: unknown; behavior?: SyncBehavior }) => {
      const key = (p.key || "").trim();
      if (!key) return;
      const behavior: SyncBehavior = p.behavior === "immediate" ? "immediate" : "debounce";
      const now = Date.now();

      const send = async (value: unknown) => {
        const docId = getDocIdRef.current().trim();
        if (!docId) return;
        const res = await senderRef.current({ docId, key, value });
        if (res.ok && typeof res.revision === "number") {
          onAckRevisionRef.current?.(res.revision);
        }
      };

      if (behavior === "immediate") {
        const existing = pendingRef.current.get(key);
        if (existing?.timer) window.clearTimeout(existing.timer);
        pendingRef.current.set(key, { timer: null, value: p.value, lastQueuedAt: now });
        void send(p.value);
        return;
      }

      const cur = pendingRef.current.get(key) ?? { timer: null, value: undefined, lastQueuedAt: 0 };
      if (cur.timer) window.clearTimeout(cur.timer);
      cur.value = p.value;
      cur.lastQueuedAt = now;
      cur.timer = window.setTimeout(() => {
        cur.timer = null;
        void send(cur.value);
      }, debounceMs);
      pendingRef.current.set(key, cur);
    },
    [debounceMs],
  );

  const flushAll = useCallback(async () => {
    const entries = Array.from(pendingRef.current.entries());
    for (const [key, st] of entries) {
      if (st.timer) {
        window.clearTimeout(st.timer);
        st.timer = null;
      }
      await flushKey(key, st.value);
    }
    pendingRef.current.clear();
  }, [flushKey]);

  useEffect(() => {
    return () => {
      const entries = Array.from(pendingRef.current.entries());
      if (entries.length === 0) return;
      for (const [key, st] of entries) {
        if (st.timer) {
          window.clearTimeout(st.timer);
          st.timer = null;
        }
        const docId = getDocIdRef.current().trim();
        if (!docId || !key.trim()) continue;
        const req: SyncRequest = { docId, key, value: st.value };
        const ok = trySendBeacon(req);
        if (!ok) void flushViaFetchKeepalive(req);
      }
      pendingRef.current.clear();
    };
  }, [debounceMs, flushKey]);

  return { syncState, flushAll };
}

export type SkillUiRuntimeContextValue = {
  postToAgent: (text: string) => void | Promise<void>;
  /** 不入聊天流的静默触发（用于 Auto-resume 等） */
  postToAgentSilently?: (text: string) => void | Promise<void>;
  /** 将上传卡片锁定态写回聊天历史（用于刷新回放） */
  lockFilePickerCard?: (cardId: string, uploads: SduiUploadedFileRecord[]) => void;
  /** 可选：将多行文本输入卡片锁定态写回聊天历史（用于刷新回放） */
  lockHitlTextInputCard?: (cardId: string, text: string) => void;
  /**
   * Optional: send plain text back to the main chat input (non-skill context).
   * Used by present_choices inlined as ChoiceCard in the message stream.
   */
  onSendText?: (text: string, opts?: { cardId?: string; submittedValue?: string }) => void;
  getInputValue: (id: string) => string;
  setInputValue: (id: string, value: string) => void;
  openPreview: (path: string) => void;
  syncState: (args: {
    key: string;
    value: unknown;
    behavior?: "debounce" | "immediate";
  }) => void;
};

const SkillUiRuntimeContext = createContext<SkillUiRuntimeContextValue | null>(null);

type Props = {
  children: ReactNode;
  postToAgentRaw: (text: string) => void | Promise<void>;
  postToAgentSilentlyRaw?: (text: string) => void | Promise<void>;
  lockFilePickerCardRaw?: (cardId: string, uploads: SduiUploadedFileRecord[]) => void;
  lockHitlTextInputCardRaw?: (cardId: string, text: string) => void;
  onSendTextRaw?: (text: string, opts?: { cardId?: string; submittedValue?: string }) => void;
  onOpenPreview?: (path: string) => void;
  syncStateRaw?: (args: { key: string; value: unknown; behavior?: "debounce" | "immediate" }) => void;
  docId?: string;
  enableInternalSync?: boolean;
};

export function SkillUiRuntimeProvider({
  children,
  postToAgentRaw,
  postToAgentSilentlyRaw,
  lockFilePickerCardRaw,
  lockHitlTextInputCardRaw,
  onSendTextRaw,
  onOpenPreview,
  syncStateRaw,
  docId,
  enableInternalSync,
}: Props) {
  const inputsRef = useRef<Record<string, string>>({});
  const [, force] = useState(0);
  const legacyRegistry = useProjectOverviewStore((snapshot) => ({
    loaded: snapshot.registryLoaded,
    moduleIds: new Set(snapshot.registryItems.map((x) => x.moduleId)),
  }));
  const canInternal = Boolean(docId && (enableInternalSync ?? true) && !syncStateRaw);
  // Keep hook arguments stable to avoid recreating syncState every render.
  const getDocId = useCallback(() => docId ?? "", [docId]);
  const { syncState: syncStateInternal } = useSyncState({ getDocId });

  const getInputValue = useCallback((id: string) => inputsRef.current[id] ?? "", []);

  const setInputValue = useCallback((id: string, value: string) => {
    inputsRef.current[id] = value;
    force((x) => x + 1);
  }, []);

  const postToAgent = useCallback(
    (text: string) => {
      const expanded = expandInputPlaceholders(text, getInputValue);
      // Option 1 (Skill-first): module_action is a legacy escape hatch and MUST be gated by registry whitelist.
      try {
        const parsed = JSON.parse(expanded) as unknown;
        if (
          parsed &&
          typeof parsed === "object" &&
          (parsed as { type?: unknown }).type === "chat_card_intent" &&
          (parsed as { verb?: unknown }).verb === "module_action"
        ) {
          const payload = (parsed as { payload?: unknown }).payload as unknown;
          const mid =
            payload && typeof payload === "object" ? String((payload as { moduleId?: unknown }).moduleId ?? "") : "";
          const moduleId = mid.trim();
          if (!moduleId || !legacyRegistry.loaded || !legacyRegistry.moduleIds.has(moduleId)) {
            console.warn("[SkillUiRuntime] blocked legacy module_action", {
              moduleId,
              loaded: legacyRegistry.loaded,
            });
            return;
          }
        }
      } catch {
        // Not a JSON envelope; allow passthrough.
      }
      return postToAgentRaw(expanded);
    },
    [postToAgentRaw, getInputValue, legacyRegistry.loaded, legacyRegistry.moduleIds],
  );

  const postToAgentSilently = useCallback(
    (text: string) => {
      if (!postToAgentSilentlyRaw) return;
      const expanded = expandInputPlaceholders(text, getInputValue);
      // Keep the same legacy gating as postToAgent to avoid opening an unexpected escape hatch.
      try {
        const parsed = JSON.parse(expanded) as unknown;
        if (
          parsed &&
          typeof parsed === "object" &&
          (parsed as { type?: unknown }).type === "chat_card_intent" &&
          (parsed as { verb?: unknown }).verb === "module_action"
        ) {
          const payload = (parsed as { payload?: unknown }).payload as unknown;
          const mid =
            payload && typeof payload === "object" ? String((payload as { moduleId?: unknown }).moduleId ?? "") : "";
          const moduleId = mid.trim();
          if (!moduleId || !legacyRegistry.loaded || !legacyRegistry.moduleIds.has(moduleId)) {
            console.warn("[SkillUiRuntime] blocked legacy module_action (silent)", {
              moduleId,
              loaded: legacyRegistry.loaded,
            });
            return;
          }
        }
      } catch {
        // Not a JSON envelope; allow passthrough.
      }
      return postToAgentSilentlyRaw(expanded);
    },
    [postToAgentSilentlyRaw, getInputValue, legacyRegistry.loaded, legacyRegistry.moduleIds],
  );

  const openPreview = useCallback(
    (path: string) => {
      const p = path.trim();
      if (!p) return;
      if (/^https?:\/\//i.test(p)) {
        onOpenPreview?.(`browser://${p}`);
        return;
      }
      onOpenPreview?.(p);
    },
    [onOpenPreview],
  );

  const value = useMemo<SkillUiRuntimeContextValue>(
    () => ({
      postToAgent,
      postToAgentSilently,
      lockFilePickerCard: lockFilePickerCardRaw,
      lockHitlTextInputCard: lockHitlTextInputCardRaw,
      onSendText: onSendTextRaw,
      getInputValue,
      setInputValue,
      openPreview,
      syncState: (args) => {
        if (syncStateRaw) {
          syncStateRaw(args);
          return;
        }
        if (canInternal) {
          syncStateInternal(args);
        }
      },
    }),
    [
      postToAgent,
      postToAgentSilently,
      lockFilePickerCardRaw,
      lockHitlTextInputCardRaw,
      onSendTextRaw,
      getInputValue,
      setInputValue,
      openPreview,
      syncStateRaw,
      canInternal,
      syncStateInternal,
    ],
  );

  return <SkillUiRuntimeContext.Provider value={value}>{children}</SkillUiRuntimeContext.Provider>;
}

export function useSkillUiRuntime(): SkillUiRuntimeContextValue {
  const ctx = useContext(SkillUiRuntimeContext);
  if (!ctx) {
    throw new Error("useSkillUiRuntime must be used within SkillUiRuntimeProvider");
  }
  return ctx;
}
