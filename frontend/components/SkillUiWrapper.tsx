"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { buildProxiedFileUrl } from "@/lib/apiFile";
import {
  parseSkillUiPath,
  SKILL_UI_REGISTRY,
  type SkillUiComponentProps,
} from "@/lib/skillUiRegistry";
import { SkillUiRuntimeProvider } from "@/components/sdui/SkillUiRuntimeProvider";
import {
  applySduiPatch,
  parseSduiDocument,
  stripStepperNodesFromSduiDocument,
  type SduiDocument,
  type SduiPatch,
} from "@/lib/sdui";
import { normalizeSduiDocumentInput } from "@/lib/sduiNormalizer";
import type { SkillUiDataPatchEvent } from "@/hooks/useAgentChat";

const SDUI_SHELL = "SduiView";

/** job_management 大盘：平台默认不展示 SDUI Stepper（与 Skill-First / DevKit 一致；不依赖磁盘 JSON 是否仍含 Stepper） */
function isJobManagementSkillUiContext(syntheticPath: string, dataFile: string | null | undefined): boolean {
  const h = `${syntheticPath}\n${dataFile ?? ""}`.replace(/\\/g, "/");
  return h.includes("skills/job_management/");
}

function skillUiPatchDebug(message: string, extra?: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  const w = window as unknown as { __NANOBOT_DEBUG_SKILL_UI_PATCH__?: boolean };
  const enabled =
    process.env.NODE_ENV === "development" || Boolean(w.__NANOBOT_DEBUG_SKILL_UI_PATCH__);
  if (!enabled) return;
  if (extra) console.debug(`[SkillUiDataPatch] ${message}`, extra);
  else console.debug(`[SkillUiDataPatch] ${message}`);
}

type Props = {
  syntheticPath: string;
  /** 封装自 sendMessage，用于 Button / DataGrid 等回传 Intent */
  postToAgent?: (text: string) => void | Promise<void>;
  /** 不入聊天流的静默触发 */
  postToAgentSilently?: (text: string) => void | Promise<void>;
  /** Agent 是否在运行（用于下降沿强刷 dataFile） */
  isAgentRunning?: boolean;
  /** open_preview 动作打开预览 */
  onOpenPreview?: (path: string) => void;
  /** v3：单条 patch（兼容旧调用方；与 incomingPatchQueue 二选一或并存时队列优先） */
  incomingPatchEvent?: SkillUiDataPatchEvent | null;
  /** v3：本会话内同一面板的连续 patch（避免 React state 只保留最后一条导致 Stepper 等丢失） */
  incomingPatchQueue?: readonly SkillUiDataPatchEvent[] | null;
};

function UnknownSkillUiPanel({ component, hint }: { component: string; hint?: string }) {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-3 items-start"
      style={{
        border: "1px solid rgba(245,158,11,0.35)",
        background: "rgba(245,158,11,0.06)",
      }}
    >
      <div className="flex items-center gap-2 text-amber-200/90">
        <LayoutGrid size={20} />
        <span className="text-sm font-semibold">未知或未支持的 Skill UI 外壳</span>
      </div>
      <p className="text-xs ui-text-secondary leading-relaxed">
        名称 <code className="px-1 rounded bg-[var(--surface-3)] ui-text-primary">{component}</code>{" "}
        未在 <code className="px-1 rounded bg-[var(--surface-3)]">SKILL_UI_REGISTRY</code> 中注册，或不是 SDUI 顶层外壳。
      </p>
      {hint ? (
        <p className="text-[11px] ui-text-muted leading-relaxed">{hint}</p>
      ) : (
        <p className="text-[11px] ui-text-muted">
          SDUI 请使用{" "}
          <code className="ui-text-secondary">skill-ui://SduiView?dataFile=&lt;workspace 相对路径&gt;</code>，内容由 JSON 内{" "}
          <code className="ui-text-secondary">root</code> 递归渲染。
        </p>
      )}
    </div>
  );
}

/**
 * 解析 skill-ui://，仅挂载注册表中的顶层外壳（当前 SDUI 固定为 SduiView），
 * 通过 GET /api/file 拉取 dataFile JSON，并由 SduiView 按文档递归渲染。
 *
 * 混合模式 patch 路由：所有 `SkillUiDataPatch` 必须与当前面板的 `syntheticPath` 及
 * `patch.docId` 一致；服务端按 docId 单调递增 `revision`。多子任务共享同一 docId 时
 * 不得跳过队列或本地直写 state，以免低 revision 覆盖高 revision。
 */
export function SkillUiWrapper({
  syntheticPath,
  postToAgent: postToAgentProp,
  postToAgentSilently: postToAgentSilentlyProp,
  isAgentRunning = false,
  onOpenPreview,
  incomingPatchEvent = null,
  incomingPatchQueue = null,
}: Props) {
  const parsed = parseSkillUiPath(syntheticPath);
  const [data, setData] = useState<unknown>(undefined);
  const [baseDoc, setBaseDoc] = useState<SduiDocument | null>(null);
  const [loading, setLoading] = useState(() => Boolean(parseSkillUiPath(syntheticPath)?.dataFile));
  const [error, setError] = useState<string | null>(null);

  const componentName = parsed?.component?.trim() ?? "";
  const dataFile = parsed?.dataFile ?? null;

  const pendingPatchesRef = useRef<SduiPatch[]>([]);
  const lastAppliedPatchIdRef = useRef<string>("");
  const appliedPatchEventIdsRef = useRef<Set<string>>(new Set());
  const lastRevisionByDocIdRef = useRef<Map<string, number>>(new Map());
  /** tryApplyPatch 等 callback 依赖 ref，避免 [] 闭包拿到旧的 syntheticPath */
  const skillUiPathRef = useRef({ syntheticPath, dataFile });
  skillUiPathRef.current = { syntheticPath, dataFile };

  useEffect(() => {
    appliedPatchEventIdsRef.current.clear();
  }, [syntheticPath]);

  const postToAgentRaw = useCallback(
    (text: string) => {
      if (postToAgentProp) {
        return postToAgentProp(text);
      } else {
        console.warn("[SkillUiWrapper] postToAgent 未注入，忽略回传:", text.slice(0, 200));
      }
    },
    [postToAgentProp],
  );

  const postToAgentSilentlyRaw = useCallback(
    (text: string) => {
      if (postToAgentSilentlyProp) {
        return postToAgentSilentlyProp(text);
      }
      // Fallback: if silent channel not provided, degrade to normal post.
      return postToAgentRaw(text);
    },
    [postToAgentSilentlyProp, postToAgentRaw],
  );

  const loadData = useCallback(
    async () => {
      const p = parseSkillUiPath(syntheticPath);
      if (!p?.dataFile) {
        setData(undefined);
        setBaseDoc(null);
        setLoading(false);
        setError(null);
        pendingPatchesRef.current = [];
        lastRevisionByDocIdRef.current.clear();
        appliedPatchEventIdsRef.current.clear();
        return;
      }

      setLoading(true);
      setError(null);
      setData(undefined);
      setBaseDoc(null);
      pendingPatchesRef.current = [];
      lastRevisionByDocIdRef.current.clear();
      appliedPatchEventIdsRef.current.clear();

      let dataFileTried = p.dataFile.replace(/\\/g, "/");
      const tryFetch = async (rel: string) => {
        const u = `${buildProxiedFileUrl(rel)}&t=${Date.now()}`;
        return fetch(u, { cache: "no-store" });
      };

      try {
        let res = await tryFetch(dataFileTried);
        // Agent 常把文件写在 workspace 根目录，但 Skill 仍写 `workspace/foo.json` → 多一层目录 404
        if (
          !res.ok &&
          res.status === 404 &&
          /^workspace\//i.test(dataFileTried)
        ) {
          const alt = dataFileTried.replace(/^workspace\//i, "");
          if (alt && alt !== dataFileTried) {
            const second = await tryFetch(alt);
            if (second.ok) {
              res = second;
              dataFileTried = alt;
            }
          }
        }
        if (!res.ok && res.status === 404 && /(?:^|\/)data\/dashboard\.json$/i.test(dataFileTried)) {
          // Quietly ignore missing dashboards: many tool-only flows do not ship a module dashboard.
          // Render an empty doc instead of a red error box to reduce noise.
          const emptyDoc = {
            schemaVersion: 1,
            type: "SduiDocument",
            meta: { docId: "dashboard:missing", role: "dashboard" },
            root: { type: "Stack", gap: "md", children: [] },
          } as const;
          const parsedDoc = parseSduiDocument(emptyDoc);
          if (parsedDoc.ok) {
            setBaseDoc(parsedDoc.doc);
            setData(parsedDoc.doc);
          } else {
            setBaseDoc(null);
            setData(emptyDoc);
          }
          setError(null);
          return;
        }

        const text = await res.text();
        if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
        let json: unknown;
        try {
          json = text.trim() === "" ? undefined : JSON.parse(text);
        } catch {
          throw new Error("dataFile 不是合法 JSON");
        }
        // Normalize+parse once so we can apply patches reliably.
        const normalized = normalizeSduiDocumentInput(json);
        const parsedDoc = parseSduiDocument(normalized);
        if (parsedDoc.ok) {
          const doc = isJobManagementSkillUiContext(syntheticPath, dataFileTried)
            ? stripStepperNodesFromSduiDocument(parsedDoc.doc)
            : parsedDoc.doc;
          setBaseDoc(doc);
          setData(doc);
        } else {
          // Fall back to raw JSON so UI can still show validation error details.
          setBaseDoc(null);
          setData(normalized);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [syntheticPath],
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const prevRunningRef = useRef<boolean | undefined>(undefined);
  useEffect(() => {
    const prev = prevRunningRef.current;
    if (prev === true && isAgentRunning === false) {
      // 磁盘上的 dataFile 往往仍是「基线」；进度只由 SkillUiDataPatch 推入内存。
      // 若在 run 结束后再 loadData，会把 UI 打回基线（例如 0%），表现为「扫完清 0」。
      // 若本会话已应用过任意 patch，则保留内存中的最终文档，仅依赖初次 mount / syntheticPath 变化时的 loadData。
      const hadLivePatches = lastRevisionByDocIdRef.current.size > 0;
      if (!hadLivePatches) {
        void loadData();
      }
    }
    prevRunningRef.current = isAgentRunning;
  }, [isAgentRunning, loadData]);

  const tryApplyPatch = useCallback((patch: SduiPatch) => {
    setBaseDoc((cur) => {
      if (!cur) return cur;
      const docId = patch.docId.trim();
      const revision = patch.revision;
      if (!docId || typeof revision !== "number" || !Number.isFinite(revision)) {
        skillUiPatchDebug("discard: invalid docId or revision", {
          docId: patch.docId,
          revision: patch.revision,
        });
        return cur;
      }
      const last = lastRevisionByDocIdRef.current.get(docId) ?? 0;
      if (revision <= last) {
        skillUiPatchDebug("discard: revision not greater than last applied", {
          docId,
          revision,
          lastApplied: last,
        });
        return cur;
      }
      lastRevisionByDocIdRef.current.set(docId, revision);
      const raw = applySduiPatch(cur, patch);
      const { syntheticPath: sp, dataFile: df } = skillUiPathRef.current;
      const next = isJobManagementSkillUiContext(sp, df) ? stripStepperNodesFromSduiDocument(raw) : raw;
      // Defer: avoid calling setData synchronously inside setBaseDoc updater (nested updates → max depth risk).
      queueMicrotask(() => setData(next));
      skillUiPatchDebug("applied", {
        docId,
        revision,
        opCount: patch.ops?.length ?? 0,
      });
      return next;
    });
  }, []);

  const flushPatchQueue = useCallback(() => {
    const queued = pendingPatchesRef.current;
    if (!queued.length) return;
    pendingPatchesRef.current = [];
    const sorted = [...queued].sort((a, b) => a.revision - b.revision);
    setBaseDoc((cur) => {
      if (!cur) return cur;
      let doc = cur;
      for (const patch of sorted) {
        const docId = patch.docId.trim();
        const revision = patch.revision;
        if (!docId || typeof revision !== "number" || !Number.isFinite(revision)) {
          skillUiPatchDebug("queued patch skipped: invalid docId or revision", {
            docId: patch.docId,
            revision: patch.revision,
          });
          continue;
        }
        const last = lastRevisionByDocIdRef.current.get(docId) ?? 0;
        if (revision <= last) {
          skillUiPatchDebug("queued patch skipped: revision stale", {
            docId,
            revision,
            lastApplied: last,
          });
          continue;
        }
        lastRevisionByDocIdRef.current.set(docId, revision);
        doc = applySduiPatch(doc, patch);
        skillUiPatchDebug("applied (from queue)", {
          docId,
          revision,
          opCount: patch.ops?.length ?? 0,
        });
      }
      const { syntheticPath: sp, dataFile: df } = skillUiPathRef.current;
      if (isJobManagementSkillUiContext(sp, df)) {
        doc = stripStepperNodesFromSduiDocument(doc);
      }
      queueMicrotask(() => setData(doc));
      return doc;
    });
  }, []);

  // Consume incoming SSE patches; buffer if base doc not ready.
  useEffect(() => {
    const path = syntheticPath.trim();
    const q = incomingPatchQueue ?? [];

    if (q.length > 0) {
      const fresh = q.filter((e) => e.syntheticPath.trim() === path && !appliedPatchEventIdsRef.current.has(e.id));
      if (!fresh.length) return;
      for (const e of fresh) appliedPatchEventIdsRef.current.add(e.id);
      const patches = fresh.map((e) => e.patch);
      if (!baseDoc) {
        for (const patch of patches) {
          skillUiPatchDebug("buffered until base document ready", {
            docId: patch.docId,
            revision: patch.revision,
          });
          pendingPatchesRef.current.push(patch);
        }
        return;
      }
      setBaseDoc((cur) => {
        if (!cur) return cur;
        let doc = cur;
        for (const patch of patches) {
          const docId = patch.docId.trim();
          const revision = patch.revision;
          if (!docId || typeof revision !== "number" || !Number.isFinite(revision)) {
            skillUiPatchDebug("discard: invalid docId or revision", { docId: patch.docId, revision: patch.revision });
            continue;
          }
          const last = lastRevisionByDocIdRef.current.get(docId) ?? 0;
          if (revision <= last) {
            skillUiPatchDebug("discard: revision not greater than last applied", { docId, revision, lastApplied: last });
            continue;
          }
          lastRevisionByDocIdRef.current.set(docId, revision);
          doc = applySduiPatch(doc, patch);
          skillUiPatchDebug("applied (batch)", { docId, revision, opCount: patch.ops?.length ?? 0 });
        }
        const { syntheticPath: sp, dataFile: df } = skillUiPathRef.current;
        if (isJobManagementSkillUiContext(sp, df)) {
          doc = stripStepperNodesFromSduiDocument(doc);
        }
        queueMicrotask(() => setData(doc));
        return doc;
      });
      return;
    }

    if (!incomingPatchEvent) return;
    if (incomingPatchEvent.id === lastAppliedPatchIdRef.current) return;

    if (incomingPatchEvent.syntheticPath.trim() !== path) {
      skillUiPatchDebug("discard: syntheticPath mismatch", {
        panelPath: path,
        eventPath: incomingPatchEvent.syntheticPath.trim(),
      });
      return;
    }

    lastAppliedPatchIdRef.current = incomingPatchEvent.id;

    const patch = incomingPatchEvent.patch;
    if (!baseDoc) {
      skillUiPatchDebug("buffered until base document ready", {
        docId: patch.docId,
        revision: patch.revision,
      });
      pendingPatchesRef.current.push(patch);
      return;
    }
    tryApplyPatch(patch);
  }, [incomingPatchQueue, incomingPatchEvent, syntheticPath, baseDoc, tryApplyPatch]);

  // Replay buffered patches once the base doc is ready.
  useEffect(() => {
    if (!baseDoc) return;
    flushPatchQueue();
  }, [baseDoc, flushPatchQueue]);

  if (!parsed) {
    return (
      <div className="rounded-xl p-4 text-sm" style={{ color: "var(--danger)" }}>
        无法解析 Skill UI 路径，请使用{" "}
        <code className="ui-text-secondary">skill-ui://SduiView?dataFile=路径</code> 格式。
      </div>
    );
  }

  if (componentName !== SDUI_SHELL) {
    return (
      <UnknownSkillUiPanel
        component={componentName || "(空)"}
        hint={`请改为 skill-ui://${SDUI_SHELL}?dataFile=...；内部 UI 由 JSON 的 root 定义，无需改 URL 中的组件名。`}
      />
    );
  }

  const Inner = SKILL_UI_REGISTRY[SDUI_SHELL];
  if (!Inner) {
    return <UnknownSkillUiPanel component={SDUI_SHELL} />;
  }

  const injected: SkillUiComponentProps = {
    data: baseDoc ?? data,
    loading,
    error,
    dataFilePath: dataFile,
  };

  const resolvedDocId =
    baseDoc?.meta && typeof baseDoc.meta.docId === "string" ? baseDoc.meta.docId : undefined;

  return (
    <SkillUiRuntimeProvider
      postToAgentRaw={postToAgentRaw}
      postToAgentSilentlyRaw={postToAgentSilentlyRaw}
      onOpenPreview={onOpenPreview}
      docId={resolvedDocId}
      enableInternalSync
    >
      {/*
        SDUI 内常见 position:fixed + inset:0 铺满「视口」；不设包含块时会盖住 ModuleDashboard 顶栏（总览）等兄弟区域。
        transform 使 fixed 相对本容器定位，避免挡掉返回总览。
      */}
      <div className="relative h-full min-h-0 overflow-hidden isolate" style={{ transform: "translateZ(0)" }}>
        <Inner {...injected} />
      </div>
    </SkillUiRuntimeProvider>
  );
}
