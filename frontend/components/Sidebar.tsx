"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Building2, Check, ChevronLeft, ChevronRight, Copy, FileText, FolderOpen, Globe, Plus, RefreshCw, Settings, Trash2, Zap } from "lucide-react";
import { SessionList } from "@/components/SessionList";
import { ThemeToggle } from "@/components/ThemeToggle";
import type { AgentMessage, SessionSummary } from "@/hooks/useAgentChat";
import { extractIndexedFiles } from "@/lib/fileIndex";
import { openLocation } from "@/lib/apiFile";

type Props = {
  threadId: string;
  apiBase: string;
  onClear: () => void;
  onPreviewPath: (path: string) => void;
  /** Currently open preview path (null if panel is closed). Used for toggle logic. */
  currentPreviewPath?: string | null;
  /** Close the preview panel without opening a new one. */
  onClosePreview?: () => void;
  messages: AgentMessage[];
  isLoading: boolean;
  sessions: SessionSummary[];
  onCreateSession: () => void;
  onSelectSession: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
  onOpenSettings?: () => void;
  onSkillSelect?: (skillName: string) => void;
  onOpenOrgAssetDetail?: (assetId: string) => void;
  refreshNonce?: number;
  /** When true the sidebar is in 64 px icon-only mode */
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
};

type SkillItem = {
  name: string;
  skillDir: string;
  skillFile: string;
  mtimeMs: number;
  source?: string;
  /** Parsed from SKILL.md frontmatter `description:` field */
  description?: string;
  remoteSkillId?: string;
  remoteTitle?: string;
  organizationName?: string;
};

type SkillsResp = { items: SkillItem[] };
type OrgAssetItem = {
  id: string;
  title: string;
  name: string;
  description: string;
  version: string;
  organizationName: string;
  updatedAt: string;
};
type TrashModalState = { open: boolean; mode: "one" | "all"; targets: string[] };
type SkillPublishTarget = "personal" | "backflow";
type SkillPublishModalState = {
  open: boolean;
  skill: SkillItem | null;
  target: SkillPublishTarget;
};

function apiPath(path: string, apiBase: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    return `${apiBase.replace(/\/$/, "")}${path}`;
  }
  return path;
}

export function Sidebar({
  threadId,
  apiBase,
  onClear,
  onPreviewPath,
  currentPreviewPath,
  onClosePreview,
  messages,
  isLoading,
  sessions,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  onOpenSettings,
  onSkillSelect,
  onOpenOrgAssetDetail,
  refreshNonce = 0,
  isCollapsed = false,
  onToggleCollapse,
}: Props) {
  const readApiError = useCallback(
    (body: { error?: { message?: string; detail?: string } }, fallback: string) => {
      const message = body.error?.message?.trim();
      const detail = body.error?.detail?.trim();
      if (message && detail) return `${message}: ${detail}`;
      return message || detail || fallback;
    },
    [],
  );
  /**
   * Toggle helper: if *targetPath* is already open, close the panel;
   * otherwise open it.
   */
  const togglePreview = useCallback(
    (targetPath: string) => {
      if (currentPreviewPath === targetPath) {
        onClosePreview?.();
      } else {
        onPreviewPath(targetPath);
      }
    },
    [currentPreviewPath, onClosePreview, onPreviewPath],
  );
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [selectedSkillName, setSelectedSkillName] = useState<string | null>(null);
  const [hoveredSkill, setHoveredSkill] = useState<SkillItem | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ top: number; left: number } | null>(null);
  const [removedPaths, setRemovedPaths] = useState<Set<string>>(new Set());
  const [trashError, setTrashError] = useState<string | null>(null);
  const [trashBusy, setTrashBusy] = useState(false);
  const [trashModal, setTrashModal] = useState<TrashModalState>({ open: false, mode: "one", targets: [] });
  const [skillPublishModal, setSkillPublishModal] = useState<SkillPublishModalState>({
    open: false,
    skill: null,
    target: "personal",
  });
  const [skillPublishBusy, setSkillPublishBusy] = useState(false);
  const [skillPublishError, setSkillPublishError] = useState<string | null>(null);
  const [skillPublishStatus, setSkillPublishStatus] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [orgAssets, setOrgAssets] = useState<OrgAssetItem[]>([]);
  const [orgAssetsLoading, setOrgAssetsLoading] = useState(false);
  const [orgAssetsError, setOrgAssetsError] = useState<string | null>(null);
  const [orgAssetsConnected, setOrgAssetsConnected] = useState(true);
  const stableIndexedFilesRef = useRef<ReturnType<typeof extractIndexedFiles>>([]);
  const indexedFiles = useMemo(() => {
    // During streaming, freeze file-index recomputation to avoid input lag.
    if (!isLoading) {
      stableIndexedFilesRef.current = extractIndexedFiles(messages);
    }
    return stableIndexedFilesRef.current;
  }, [messages, isLoading]);
  const artifacts = useMemo(
    () => indexedFiles.filter((f) => !removedPaths.has(f.path)),
    [indexedFiles, removedPaths],
  );

  const loadSkills = useCallback(async () => {
    setSkillsLoading(true);
    setSkillsError(null);
    try {
      const res = await fetch(apiPath("/api/skills", apiBase));
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(txt || `HTTP ${res.status}`);
      }
      const j = (await res.json()) as SkillsResp;
      setSkills(j.items ?? []);
      if (selectedSkillName && !(j.items ?? []).some((x) => x.name === selectedSkillName)) {
        setSelectedSkillName(null);
      }
    } catch (e) {
      setSkillsError(e instanceof Error ? e.message : String(e));
    } finally {
      setSkillsLoading(false);
    }
  }, [apiBase, selectedSkillName]);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills, refreshNonce]);

  const loadOrgAssets = useCallback(async () => {
    setOrgAssetsLoading(true);
    setOrgAssetsError(null);
    try {
      const res = await fetch(apiPath("/api/remote-assets/org-skills", apiBase));
      const body = (await res.json().catch(() => ({}))) as { items?: OrgAssetItem[]; error?: { code?: string; message?: string } };
      if (!res.ok) {
        if (body.error?.code === "remote_not_connected") {
          setOrgAssetsConnected(false);
          setOrgAssets([]);
          return;
        }
        throw new Error(body.error?.message ?? `HTTP ${res.status}`);
      }
      setOrgAssetsConnected(true);
      setOrgAssets(body.items ?? []);
    } catch (e) {
      setOrgAssetsConnected(true);
      setOrgAssetsError(e instanceof Error ? e.message : String(e));
    } finally {
      setOrgAssetsLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    void loadOrgAssets();
  }, [loadOrgAssets, refreshNonce]);

  const copyPath = useCallback((path: string) => {
    void navigator.clipboard.writeText(path).then(() => {
      setCopiedPath(path);
      setTimeout(() => setCopiedPath(null), 1400);
    });
  }, []);

  const handleOpenLocation = useCallback(async (path: string) => {
    try {
      await openLocation(path);
    } catch {
      // silently ignore — OS might open despite a network error
    }
  }, []);

  const submitTrash = useCallback(async () => {
    if (!trashModal.targets.length) return;
    setTrashBusy(true);
    setTrashError(null);
    try {
      const res = await fetch(apiPath("/api/trash-files", apiBase), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: trashModal.targets }),
      });
      const txt = await res.text();
      let payload: {
        deleted?: string[];
        failed?: Array<{ path?: string; reason?: string }>;
        error?: { message?: string };
      } = {};
      try {
        payload = txt ? (JSON.parse(txt) as typeof payload) : {};
      } catch {
        payload = {};
      }
      if (!res.ok) {
        throw new Error(payload.error?.message || txt || `HTTP ${res.status}`);
      }
      const deleted = payload.deleted ?? [];
      const failed = payload.failed ?? [];
      setRemovedPaths((prev) => {
        const next = new Set(prev);
        for (const p of deleted) next.add(p);
        return next;
      });
      if (failed.length > 0) {
        setTrashError(`已删 ${deleted.length} 项，失败 ${failed.length} 项（失败项保留）。`);
      } else {
        setTrashModal({ open: false, mode: "one", targets: [] });
      }
    } catch (e) {
      setTrashError(e instanceof Error ? e.message : String(e));
    } finally {
      setTrashBusy(false);
    }
  }, [apiBase, trashModal.targets]);

  const submitSkillPublish = useCallback(async () => {
    if (!skillPublishModal.skill) return;
    setSkillPublishBusy(true);
    setSkillPublishError(null);
    setSkillPublishStatus(null);
    try {
      const res = await fetch(apiPath("/api/skills/publish", apiBase), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          skillName: skillPublishModal.skill.name,
          target: skillPublishModal.target,
        }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        target?: SkillPublishTarget;
        item?: { title?: string };
        error?: { message?: string; detail?: string };
      };
      if (!res.ok) {
        throw new Error(readApiError(body, `HTTP ${res.status}`));
      }
      if (body.target === "backflow") {
        setSkillPublishStatus(`已回收到远端项目资产：${body.item?.title ?? skillPublishModal.skill.name}`);
      } else {
        setSkillPublishStatus(`已上传为个人资产：${body.item?.title ?? `${skillPublishModal.skill.name}.zip`}`);
      }
      setSkillPublishModal({ open: false, skill: null, target: "personal" });
    } catch (e) {
      setSkillPublishError(e instanceof Error ? e.message : String(e));
    } finally {
      setSkillPublishBusy(false);
    }
  }, [apiBase, readApiError, skillPublishModal]);

  // ── Mini sidebar (collapsed mode) ──────────────────────────────────────
  if (isCollapsed) {
    const iconBtn = "rounded-lg p-2 ui-text-muted hover:bg-[var(--surface-3)] hover:ui-text-primary transition-colors w-10 h-10 flex items-center justify-center";
    return (
      <aside className="h-full min-h-0 rounded-none flex flex-col items-center py-3 gap-1 overflow-hidden bg-transparent border-0 shadow-none">
        {/* Logo */}
        <span className="text-lg leading-none mb-0.5" aria-hidden="true">🦞</span>
        <span className="w-1.5 h-1.5 rounded-full mb-2" style={{ background: "var(--success)" }} title="已连接" />

        {/* New session */}
        <button type="button" onClick={onCreateSession} title="新建会话" className={iconBtn}>
          <Plus size={15} />
        </button>

        {/* Artifacts — click to expand sidebar */}
        <div className="relative" title={`产物 (${artifacts.length})，点击展开`}>
          <button type="button" onClick={onToggleCollapse} className={iconBtn}>
            <FileText size={15} />
          </button>
          {artifacts.length > 0 && (
            <span className="absolute top-1 right-1 w-3.5 h-3.5 rounded-full text-[8px] font-bold flex items-center justify-center text-white pointer-events-none" style={{ background: "var(--accent)" }}>
              {artifacts.length > 9 ? "9+" : artifacts.length}
            </span>
          )}
        </div>

        {/* Skills — click to expand sidebar */}
        <button type="button" title="技能，点击展开" onClick={onToggleCollapse} className={iconBtn}>
          <Zap size={15} />
        </button>

        {/* Org Assets — click to expand sidebar */}
        <button type="button" title="组织资产，点击展开" onClick={onToggleCollapse} className={iconBtn}>
          <Building2 size={15} />
        </button>

        {/* Bottom */}
        <div className="mt-auto flex flex-col items-center gap-1">
          <button type="button" onClick={onOpenSettings} title="设置" className={iconBtn}>
            <Settings size={13} />
          </button>
          <ThemeToggle vertical />
          <button
            type="button"
            onClick={onToggleCollapse}
            title="展开侧栏"
            className={iconBtn}
            aria-label="展开侧栏"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="h-full min-h-0 overflow-y-auto rounded-none p-4 flex flex-col gap-0 bg-transparent border-0 shadow-none">
      <div className="flex items-center gap-2">
        <span className="text-base leading-none shrink-0" aria-hidden="true">🦞</span>
        <span className="font-semibold text-sm ui-text-primary leading-tight">
          AI应用使能 <span className="text-[var(--accent)]">交付claw</span>
        </span>
        <span className="ml-auto w-2 h-2 rounded-full shrink-0" style={{ background: "var(--success)" }} title="已连接" />
      </div>
      <p className="text-[10px] font-mono ui-text-muted truncate -mt-2 select-all" title={threadId || "尚未建立会话"}>
        {threadId ? threadId.slice(0, 8) + "…" + threadId.slice(-4) : "—"}
      </p>

      <SessionList
        currentThreadId={threadId}
        sessions={sessions}
        onCreate={onCreateSession}
        onSelect={onSelectSession}
        onDelete={onDeleteSession}
      />

      <section className="mt-6 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] whitespace-nowrap">
            产物 <span className="font-normal normal-case tracking-normal opacity-90">Artifacts</span>
          </span>
          <button
            type="button"
            disabled={artifacts.length === 0}
            onClick={() => {
              setTrashError(null);
              setTrashModal({ open: true, mode: "all", targets: artifacts.map((f) => f.path) });
            }}
            className="ui-btn-ghost inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs disabled:opacity-40"
            aria-label="清空最近产物并移入回收站"
          >
            <Trash2 size={12} />
            清空
          </button>
        </div>

        <div className="max-h-[200px] overflow-y-auto overflow-x-hidden space-y-0.5">
          {artifacts.length === 0 ? (
            <p className="text-[11px] ui-text-muted">本轮生成的文件会出现在这里，点击后统一在右侧预览。</p>
          ) : (
            artifacts.map((artifact, index) => (
              <div key={artifact.path} className="flex items-center gap-1 rounded-md px-2 py-1.5 hover:bg-[var(--surface-3)] transition-colors group">
                <button
                  type="button"
                  onClick={() => togglePreview(artifact.path)}
                  className="flex-1 text-left flex items-center gap-1.5 min-w-0"
                  title={artifact.path}
                >
                  <FileText size={12} className="ui-text-muted shrink-0" />
                  <span className="truncate text-xs ui-text-primary">{artifact.fileName}</span>
                  {index === 0 && (
                    <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px]" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>新</span>
                  )}
                </button>
                {/* 悬浮操作组：复制路径 / 打开位置 / 删除 */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  <button
                    type="button"
                    onClick={() => copyPath(artifact.path)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`复制路径 ${artifact.fileName}`}
                    title="复制路径"
                  >
                    {copiedPath === artifact.path
                      ? <Check size={11} style={{ color: "var(--success)" }} />
                      : <Copy size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleOpenLocation(artifact.path)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`打开位置 ${artifact.fileName}`}
                    title="打开所在位置"
                  >
                    <FolderOpen size={11} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setTrashError(null);
                      setTrashModal({ open: true, mode: "one", targets: [artifact.path] });
                    }}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`删除 ${artifact.fileName}`}
                    title="移入回收站"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="mt-6 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] whitespace-nowrap">
            技能 <span className="font-normal normal-case tracking-normal opacity-90">Skills</span>
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => {
                // If a browser panel is already open, toggle it closed
                if (currentPreviewPath?.startsWith("browser://")) {
                  onClosePreview?.();
                  return;
                }
                const input = window.prompt("请输入目标网址", "https://");
                if (!input?.trim()) return;
                onPreviewPath("browser://" + input.trim());
              }}
              className="ui-btn-ghost inline-flex items-center rounded-lg p-1.5"
              aria-label={currentPreviewPath?.startsWith("browser://") ? "关闭云端浏览器" : "打开云端浏览器"}
              title={currentPreviewPath?.startsWith("browser://") ? "关闭云端浏览器" : "打开云端浏览器"}
            >
              <Globe size={12} className={currentPreviewPath?.startsWith("browser://") ? "text-[var(--accent)]" : ""} />
            </button>
            <button
              type="button"
              onClick={() => void loadSkills()}
              className="ui-btn-ghost inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs"
              aria-label="刷新技能列表"
              title="刷新技能列表"
            >
              <RefreshCw size={12} className={skillsLoading ? "animate-spin" : ""} />
              刷新
            </button>
          </div>
        </div>

        {skillsError && (
          <p className="rounded-lg px-2 py-1 text-[11px]" style={{ background: "rgba(239,107,115,0.12)", color: "var(--danger)", border: "1px solid rgba(239,107,115,0.24)" }}>
            {skillsError}
          </p>
        )}
        {skillPublishStatus && (
          <p className="rounded-lg px-2 py-1 text-[11px]" style={{ background: "rgba(34,197,94,0.12)", color: "var(--success)", border: "1px solid rgba(34,197,94,0.24)" }}>
            {skillPublishStatus}
          </p>
        )}
        {skillPublishError && (
          <p className="rounded-lg px-2 py-1 text-[11px]" style={{ background: "rgba(239,107,115,0.12)", color: "var(--danger)", border: "1px solid rgba(239,107,115,0.24)" }}>
            {skillPublishError}
          </p>
        )}

        <div className="max-h-44 overflow-y-auto overflow-x-hidden space-y-0.5" role="list">
          {!skillsLoading && skills.length === 0 && (
            <p className="text-[11px] ui-text-muted">暂无技能（已自动创建 skills 目录）。</p>
          )}
          {skills.map((s) => {
            const isActive = selectedSkillName === s.name;
            return (
              /* div wrapper 允许在内部嵌套多个 button（button 内不能嵌套 button） */
              <div
                key={s.name}
                role="listitem"
                onMouseEnter={(e) => {
                  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                  setHoveredSkill(s);
                  setTooltipPos({ top: rect.top, left: rect.right + 8 });
                }}
                onMouseLeave={() => {
                  setHoveredSkill(null);
                  setTooltipPos(null);
                }}
                className={
                  "relative rounded-md border border-transparent transition-colors group " +
                  (isActive
                    ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]/40"
                    : "hover:bg-[var(--surface-3)]")
                }
              >
                <button
                  type="button"
                  onClick={() => {
                    setSkillPublishError(null);
                    setSkillPublishStatus(null);
                    if (currentPreviewPath === s.skillFile) {
                      setSelectedSkillName(null);
                      onClosePreview?.();
                    } else {
                      setSelectedSkillName(s.name);
                      onPreviewPath(s.skillFile);
                      onSkillSelect?.(s.name);
                    }
                  }}
                  className="w-full text-left px-2.5 py-2 text-sm ui-text-secondary pr-6 group-hover:pr-28 flex items-center gap-1.5 min-w-0 transition-[padding]"
                >
                  <span className="truncate">{s.name}</span>
                  {s.source === "remote-imported" ? (
                    <span className="shrink-0 rounded px-1 py-0.5 text-[9px] font-medium leading-none border border-[var(--border-subtle)] text-[var(--accent)]">
                      remote
                    </span>
                  ) : (
                    <span className="shrink-0 rounded px-1 py-0.5 text-[9px] font-medium leading-none ui-text-muted border border-[var(--border-subtle)]">
                      local
                    </span>
                  )}
                </button>
                {/* 悬浮操作组：上传/回收 / 复制路径 / 打开位置 */}
                <div className="absolute right-1 top-0 bottom-0 flex items-center gap-0.5 pr-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={() => {
                      setSkillPublishError(null);
                      setSkillPublishStatus(null);
                      setSkillPublishModal({
                        open: true,
                        skill: s,
                        target: s.source === "remote-imported" ? "backflow" : "personal",
                      });
                    }}
                    className="ui-btn-ghost rounded px-1.5 py-1 text-[10px]"
                    aria-label={`${s.source === "remote-imported" ? "回收" : "上传"} ${s.name}`}
                    title={s.source === "remote-imported" ? "回收到远端" : "上传到远端"}
                  >
                    {s.source === "remote-imported" ? "回收" : "上传"}
                  </button>
                  <button
                    type="button"
                    onClick={() => copyPath(s.skillFile)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`复制路径 ${s.name}`}
                    title="复制文件路径"
                  >
                    {copiedPath === s.skillFile
                      ? <Check size={11} style={{ color: "var(--success)" }} />
                      : <Copy size={11} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleOpenLocation(s.skillFile)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`打开位置 ${s.name}`}
                    title="打开所在位置"
                  >
                    <FolderOpen size={11} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

      </section>

      {/* ── 组织资产 Organization Assets ── */}
      <section className="mt-6 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] whitespace-nowrap">
            组织资产 <span className="font-normal normal-case tracking-normal opacity-90">Org Assets</span>
          </span>
          <button
            type="button"
            onClick={() => void loadOrgAssets()}
            className="ui-btn-ghost inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs"
            aria-label="刷新组织资产"
            title="刷新组织资产"
          >
            <RefreshCw size={12} className={orgAssetsLoading ? "animate-spin" : ""} />
            刷新
          </button>
        </div>
        {!orgAssetsConnected ? (
          <div
            className="flex flex-col items-center justify-center gap-2 py-4 rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-3)]/50 dark:bg-black/20"
          >
            <span className="text-xl" aria-hidden="true">🏛️</span>
            <p className="text-[11px] ui-text-muted text-center leading-relaxed px-2">
              远端组织资产未连接
              <br />
              <span className="text-[10px]">请先在设置中登录组织中心</span>
            </p>
            <button type="button" onClick={onOpenSettings} className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs">
              去连接
            </button>
          </div>
        ) : orgAssetsError ? (
          <p className="rounded-lg px-2 py-2 text-[11px]" style={{ background: "rgba(239,107,115,0.12)", color: "var(--danger)", border: "1px solid rgba(239,107,115,0.24)" }}>
            {orgAssetsError}
          </p>
        ) : (
          <div className="max-h-44 overflow-y-auto overflow-x-hidden space-y-2">
            {!orgAssetsLoading && orgAssets.length === 0 ? (
              <div
                className="flex flex-col items-center justify-center gap-1.5 py-4 rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-3)]/50 dark:bg-black/20"
              >
                <span className="text-xl" aria-hidden="true">🏛️</span>
                <p className="text-[11px] ui-text-muted text-center leading-relaxed px-2">当前没有可展示的组织资产。</p>
              </div>
            ) : (
              orgAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="rounded-lg p-2.5 flex flex-col gap-2 transition-colors hover:bg-[var(--surface-3)] border border-transparent"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-medium ui-text-primary truncate">{asset.title || asset.name}</p>
                    <p className="text-[11px] ui-text-muted mt-1 line-clamp-2">{asset.description || asset.organizationName || "组织资产"}</p>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] ui-text-muted">v{asset.version || "未标注"}</span>
                    <button
                      type="button"
                      onClick={() => onOpenOrgAssetDetail?.(asset.id)}
                      className="ui-btn-ghost rounded-lg px-2 py-1 text-[11px]"
                    >
                      查看详情
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </section>

      {trashModal.open && (
        <div className="mt-4 rounded-xl p-3 text-xs space-y-2 shadow-sm border border-amber-500/25 dark:border-amber-400/20 bg-amber-500/[0.08] dark:bg-amber-400/[0.06]">
          <p className="ui-text-primary">
            {trashModal.mode === "all"
              ? `确认将 ${trashModal.targets.length} 个产物移入回收站？`
              : "确认将该产物移入回收站？"}
          </p>
          {trashError && <p style={{ color: "var(--danger)" }}>{trashError}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={trashBusy}
              onClick={() => void submitTrash()}
              className="rounded-lg px-3 py-1.5 text-white disabled:opacity-50"
              style={{ background: "var(--warning)" }}
            >
              {trashBusy ? "处理中..." : "确认"}
            </button>
            <button
              type="button"
              disabled={trashBusy}
              onClick={() => setTrashModal({ open: false, mode: "one", targets: [] })}
              className="ui-btn-ghost rounded-lg px-3 py-1.5"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {skillPublishModal.open && skillPublishModal.skill && (
        <div className="mt-4 rounded-xl p-3 text-xs space-y-3 shadow-sm border border-blue-500/25 dark:border-blue-400/20 bg-blue-500/[0.08] dark:bg-blue-400/[0.06]">
          <div className="space-y-1">
            <p className="ui-text-primary font-medium">
              {skillPublishModal.skill.source === "remote-imported" ? "回收 Skill" : "上传 Skill"}
            </p>
            <p className="ui-text-muted break-all">{skillPublishModal.skill.name}</p>
          </div>
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="skill-publish-target"
                checked={skillPublishModal.target === "personal"}
                onChange={() => setSkillPublishModal((prev) => ({ ...prev, target: "personal" }))}
              />
              上传为个人资产
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="skill-publish-target"
                checked={skillPublishModal.target === "backflow"}
                disabled={skillPublishModal.skill.source !== "remote-imported"}
                onChange={() => setSkillPublishModal((prev) => ({ ...prev, target: "backflow" }))}
              />
              提交组织中心回流申请
            </label>
          </div>
          {skillPublishModal.skill.source !== "remote-imported" && (
            <p className="ui-text-muted">仅从远端导入的 skill 支持按 demo 语义回收到远端项目资产。</p>
          )}
          {skillPublishModal.skill.source === "remote-imported" && skillPublishModal.skill.remoteTitle ? (
            <p className="ui-text-muted">
              远端来源：{skillPublishModal.skill.remoteTitle}
              {skillPublishModal.skill.organizationName ? ` / ${skillPublishModal.skill.organizationName}` : ""}
            </p>
          ) : null}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={skillPublishBusy}
              onClick={() => void submitSkillPublish()}
              className="rounded-lg px-3 py-1.5 text-white disabled:opacity-50"
              style={{ background: "var(--accent)" }}
            >
              {skillPublishBusy ? "处理中..." : "确认"}
            </button>
            <button
              type="button"
              disabled={skillPublishBusy}
              onClick={() => setSkillPublishModal({ open: false, skill: null, target: "personal" })}
              className="ui-btn-ghost rounded-lg px-3 py-1.5"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* ── Bottom control bar ── */}
      <div
        className="mt-6 -mx-4 px-3 pt-4 pb-1 flex items-center gap-1 border-t border-[var(--border-subtle)]"
      >
        {/* Clear session — ghost, destructive on hover */}
        <button
          type="button"
          onClick={onClear}
          className="flex-1 flex flex-row items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs ui-text-muted transition-colors hover:bg-[var(--surface-3)] hover:text-red-500"
          title="清空当前会话"
        >
          <Trash2 size={12} className="shrink-0" />
          <span className="whitespace-nowrap">清空会话</span>
        </button>

        {/* Settings */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="
            rounded-lg p-2 ui-text-muted transition-colors shrink-0
            hover:bg-[var(--surface-3)] hover:ui-text-primary
          "
          aria-label="打开设置"
          title="设置"
        >
          <Settings size={13} />
        </button>

        {/* Theme toggle */}
        <ThemeToggle />

        {/* Collapse sidebar */}
        {onToggleCollapse && (
          <button
            type="button"
            onClick={onToggleCollapse}
            className="rounded-lg p-2 ui-text-muted transition-colors shrink-0 hover:bg-[var(--surface-3)] hover:ui-text-primary"
            aria-label="收起左侧栏"
            title="收起左侧栏"
          >
            <ChevronLeft size={13} />
          </button>
        )}
      </div>
      {/* Fixed-position skill description tooltip — unaffected by overflow clipping */}
      {hoveredSkill?.description && tooltipPos && (
        <div
          className="pointer-events-none fixed z-[9999] w-60 rounded-lg px-3 py-2.5 text-[11px] leading-relaxed shadow-xl animate-in fade-in duration-100"
          style={{
            top: tooltipPos.top,
            left: tooltipPos.left,
            background: "var(--surface-1)",
            border: "1px solid var(--border-subtle)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            maxWidth: "240px",
          }}
          aria-hidden="true"
        >
          <p className="font-semibold ui-text-primary mb-1 text-[11px]">{hoveredSkill.name}</p>
          <p className="ui-text-secondary leading-snug">{hoveredSkill.description}</p>
        </div>
      )}
    </aside>
  );
}
