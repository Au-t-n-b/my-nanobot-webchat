"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Building2, Check, ChevronRight, Copy, FileText, FolderOpen, Globe, Plus, RefreshCw, Settings, Trash2, Zap } from "lucide-react";
import { CenteredConfirmModal, CenteredModal } from "@/components/CenteredModal";
import { SessionList } from "@/components/SessionList";
import type { AgentMessage, SessionSummary, TrashedSessionV1 } from "@/hooks/useAgentChat";
import { extractIndexedFiles } from "@/lib/fileIndex";
import { openLocation } from "@/lib/apiFile";
import { SIDEBAR_SECTION_LABEL_CLASS } from "@/lib/sidebarTokens";
type Props = {
  threadId: string;
  apiBase: string;
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
  /** 产物中心：打开首个产物预览或展开侧栏（与顶栏原行为一致） */
  onOpenArtifactsHub?: () => void;
  /** 技能中心：展开侧栏展示技能列表 */
  onOpenSkillsHub?: () => void;
  /** Opens quick settings (e.g. control center settings tab). */
  onOpenQuickSettings?: () => void;
  /** Local demo auth: sign out and return to login. */
  onLogout?: () => void;
  /** 清空会话 30 天可恢复的回收项 */
  trashedSessions?: TrashedSessionV1[];
  onRestoreTrashed?: (e: TrashedSessionV1) => void;
  onDismissTrashed?: (e: TrashedSessionV1) => void;
  /** 嵌入移动端抽屉等容器时去掉外层圆角/阴影，避免与父级双圆角同色 */
  embedded?: boolean;
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
  onOpenArtifactsHub,
  onOpenSkillsHub,
  onOpenQuickSettings,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- Logout 入口已迁入 SettingsHub，保留 prop 以维持外部签名兼容
  onLogout: _onLogout,
  trashedSessions = [],
  onRestoreTrashed,
  onDismissTrashed,
  embedded = false,
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

  const asideFrameClass = embedded
    ? "flex h-full min-h-0 overflow-hidden !rounded-none !shadow-none !ring-0 border-transparent bg-[var(--canvas-rail)] dark:border-transparent"
    : "flex h-full min-h-0 overflow-hidden rounded-2xl border-r border-transparent bg-[var(--canvas-rail)] ui-elevation-1";

  // ── Mini sidebar (collapsed mode) ──────────────────────────────────────
  if (isCollapsed) {
    const iconBtn = "nav-icon-btn";
    return (
      <aside className={`${asideFrameClass} flex-col items-center gap-1 py-3`}>
        <span className="text-lg leading-none mb-0.5" aria-hidden="true">
          🦞
        </span>

        <button type="button" onClick={onCreateSession} title="新建会话" className={iconBtn}>
          <Plus size={18} />
        </button>

        <div
          className="relative"
          title={
            artifacts.length > 0
              ? `产物中心（${artifacts.length}），点击打开预览`
              : "产物中心（暂无产物时展开侧栏）"
          }
        >
          <button
            type="button"
            onClick={() => {
              if (onOpenArtifactsHub) onOpenArtifactsHub();
              else onToggleCollapse?.();
            }}
            className={iconBtn}
            aria-label="产物中心"
          >
            <FileText size={18} />
          </button>
          {artifacts.length > 0 && (
            <span
              className="pointer-events-none absolute right-1 top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full text-[8px] font-bold text-white"
              style={{ background: "color-mix(in oklab, var(--accent) 65%, transparent)" }}
            >
              {artifacts.length > 9 ? "9+" : artifacts.length}
            </span>
          )}
        </div>

        <button
          type="button"
          title="技能中心"
          onClick={() => {
            if (onOpenSkillsHub) onOpenSkillsHub();
            else onToggleCollapse?.();
          }}
          className={iconBtn}
          aria-label="技能中心"
        >
          <Zap size={18} />
        </button>

        <button type="button" title="组织资产，点击展开" onClick={onToggleCollapse} className={iconBtn}>
          <Building2 size={18} />
        </button>

        <div className="mt-auto flex flex-col items-center gap-1">
          {onOpenQuickSettings ? (
            <button
              type="button"
              onClick={onOpenQuickSettings}
              title="设置"
              className={iconBtn}
              aria-label="设置"
            >
              <Settings size={18} />
            </button>
          ) : null}
          <button
            type="button"
            onClick={onToggleCollapse}
            title="展开侧栏"
            className={iconBtn}
            aria-label="展开侧栏"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </aside>
    );
  }

  const settingsBtnClass =
    "w-full min-w-0 inline-flex items-center justify-start gap-2 rounded-lg border border-transparent bg-transparent px-3 py-2 text-[12px] font-medium ui-text-muted ui-hover-soft";

  const portalTrashModal = (
    <CenteredConfirmModal
      open={trashModal.open}
      title="移入回收站"
      variant="warning"
      loading={trashBusy}
      description={
        <div className="space-y-2">
          <p>
            {trashModal.mode === "all"
              ? `确认将 ${trashModal.targets.length} 个产物移入回收站？`
              : "确认将该产物移入回收站？"}
          </p>
          {trashError ? <p style={{ color: "var(--danger)" }}>{trashError}</p> : null}
        </div>
      }
      onCancel={() => {
        if (trashBusy) return;
        setTrashModal({ open: false, mode: "one", targets: [] });
        setTrashError(null);
      }}
      onConfirm={() => void submitTrash()}
    />
  );

  const portalSkillModal = skillPublishModal.open && skillPublishModal.skill ? (
    <CenteredModal
      open
      onClose={() => {
        if (skillPublishBusy) return;
        setSkillPublishModal({ open: false, skill: null, target: "personal" });
      }}
      title={skillPublishModal.skill.source === "remote-imported" ? "回收 Skill" : "上传 Skill"}
      disableDismiss={skillPublishBusy}
      panelClassName="w-full max-w-md"
    >
      <div className="space-y-3 text-[12px]">
        <p className="ui-text-muted break-all text-[10px]">{skillPublishModal.skill.name}</p>
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
        {skillPublishError ? <p className="text-[10px] text-[var(--danger)]">{skillPublishError}</p> : null}
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            disabled={skillPublishBusy}
            onClick={() => void submitSkillPublish()}
            className="rounded-lg px-3 py-1.5 text-white text-[12px] disabled:opacity-50"
            style={{ background: "var(--accent)" }}
          >
            {skillPublishBusy ? "处理中..." : "确认"}
          </button>
          <button
            type="button"
            disabled={skillPublishBusy}
            onClick={() => setSkillPublishModal({ open: false, skill: null, target: "personal" })}
            className="ui-btn-ghost rounded-lg px-3 py-1.5 text-[12px]"
          >
            取消
          </button>
        </div>
      </div>
    </CenteredModal>
  ) : null;

  return (
    <>
      <aside className={`${asideFrameClass} flex-col gap-0 px-4 pt-4 pb-4`}>
        {/* ── SidebarHeader：logo + 主 CTA "新建会话"（accent，最高视觉权重） ── */}
        <div className="shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-xl leading-none shrink-0 select-none" aria-hidden="true">
              🦞
            </span>
            <span className="min-w-0 flex-1 truncate font-semibold text-sm leading-tight ui-text-primary">
              AI应用使能 <span className="ui-text-muted">交付claw</span>
            </span>
          </div>
          <button
            type="button"
            onClick={onCreateSession}
            className="ui-motion mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-black bg-[var(--accent)] hover:brightness-110"
          >
            <Plus size={16} strokeWidth={2.25} aria-hidden />
            <span>新建会话</span>
          </button>
        </div>

        <div className="min-h-0 flex-1 touch-pan-y overflow-y-auto overflow-x-hidden pr-0 [overscroll-behavior-y:auto] [scrollbar-gutter:stable]">
          <div className="flex flex-col gap-6 pb-2 pt-4">
            {/* ── SidebarPrimary：会话列表 + 最近清空 ── */}
            <SessionList
              currentThreadId={threadId}
              sessions={sessions}
              onCreate={onCreateSession}
              onSelect={onSelectSession}
              onDelete={onDeleteSession}
              hideCreate
            />

            {trashedSessions.length > 0 && onRestoreTrashed && onDismissTrashed ? (
              <section className="flex flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-white/[0.02] px-3 py-2.5">
                <div className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>最近清空（30 天）</div>
                <ul className="max-h-40 space-y-0 overflow-y-auto [scrollbar-width:thin]">
                  {trashedSessions.map((e) => (
                    <li
                      key={`${e.sessionId}-${e.trashedAt}`}
                      className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-[12px]"
                    >
                      <span className="min-w-0 flex-1 truncate" title={e.title}>
                        {e.title} · {e.messageCount} 条
                      </span>
                      <button
                        type="button"
                        onClick={() => onRestoreTrashed(e)}
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)] hover:underline"
                      >
                        恢复
                      </button>
                      <button
                        type="button"
                        onClick={() => onDismissTrashed(e)}
                        className="shrink-0 text-[10px] ui-text-muted hover:text-[var(--text-primary)]"
                        title="从列表移除"
                        aria-label="从回收条移除"
                      >
                        移除
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {/* ── SidebarSecondary §产物：默认展开，最常用 ── */}
            <details className="group/details flex flex-col gap-2 min-h-0 [&_summary::-webkit-details-marker]:hidden" open>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-md px-1 py-1 ui-hover-soft">
                <span className="flex items-center gap-1.5 min-w-0">
                  <ChevronRight size={12} strokeWidth={2.25} className="shrink-0 ui-text-muted ui-motion-fast group-open/details:rotate-90" aria-hidden />
                  <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>产物</span>
                  <span className="ml-1 tabular-nums text-[10px] ui-text-secondary">{artifacts.length}</span>
                </span>
                <button
                  type="button"
                  disabled={artifacts.length === 0}
                  onClick={(e) => {
                    e.preventDefault();
                    setTrashError(null);
                    setTrashModal({ open: true, mode: "all", targets: artifacts.map((f) => f.path) });
                  }}
                  className="inline-flex items-center justify-center rounded-lg p-1.5 ui-text-muted ui-hover-soft disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="清空最近产物并移入回收站"
                  title="清空最近产物"
                >
                  <Trash2 size={16} strokeWidth={2} aria-hidden />
                </button>
              </summary>

        <div className="max-h-48 overflow-y-auto overflow-x-hidden space-y-0 [scrollbar-width:thin]">
          {artifacts.length === 0 ? (
            <p className="text-[10px] text-[var(--text-muted)]/70">暂无产物，生成后可在右侧预览。</p>
          ) : (
            artifacts.map((artifact, index) => (
              <div
                key={artifact.path}
                className={
                  "group relative flex items-center gap-2 rounded-lg px-3 py-2 ui-motion-fast " +
                  (currentPreviewPath === artifact.path ? "bg-[var(--surface-1)]" : "ui-hover-soft")
                }
              >
                {currentPreviewPath === artifact.path ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-[var(--accent)]"
                  />
                ) : null}
                <button
                  type="button"
                  onClick={() => togglePreview(artifact.path)}
                  className="flex-1 text-left flex items-center gap-1.5 min-w-0"
                  title={artifact.path}
                >
                  <FileText size={18} strokeWidth={currentPreviewPath === artifact.path ? 2.25 : 1.75} className="ui-text-muted shrink-0" />
                  <span className="truncate text-[12px] ui-text-primary">{artifact.fileName}</span>
                  {index === 0 && (
                    <span className="shrink-0 rounded px-1 py-0.5 text-[10px] font-medium tracking-[0.12em] border border-[var(--border-subtle)] ui-text-secondary">
                      新
                    </span>
                  )}
                </button>
                {/* 悬浮操作组：复制路径 / 打开位置 / 删除 —— 键盘 focus 也能显示 */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 ui-motion-fast shrink-0">
                  <button
                    type="button"
                    onClick={() => copyPath(artifact.path)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`复制路径 ${artifact.fileName}`}
                    title="复制路径"
                  >
                    {copiedPath === artifact.path
                      ? <Check size={18} strokeWidth={2.25} style={{ color: "var(--accent)" }} />
                      : <Copy size={18} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleOpenLocation(artifact.path)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`打开位置 ${artifact.fileName}`}
                    title="打开所在位置"
                  >
                    <FolderOpen size={18} />
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
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
            </details>

            {/* ── SidebarSecondary §技能：默认折叠 ── */}
            <details className="group/details flex flex-col gap-2 min-h-0 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-md px-1 py-1 ui-hover-soft">
                <span className="flex items-center gap-1.5 min-w-0">
                  <ChevronRight size={12} strokeWidth={2.25} className="shrink-0 ui-text-muted ui-motion-fast group-open/details:rotate-90" aria-hidden />
                  <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>技能</span>
                  <span className="ml-1 tabular-nums text-[10px] ui-text-secondary">{skills.length}</span>
                </span>
                <div className="flex items-center gap-1" onClick={(e) => e.preventDefault()}>
            <button
              type="button"
              onClick={() => {
                if (currentPreviewPath?.startsWith("browser://")) {
                  onClosePreview?.();
                  return;
                }
                const input = window.prompt("请输入目标网址", "https://");
                if (!input?.trim()) return;
                onPreviewPath("browser://" + input.trim());
              }}
              className="inline-flex items-center rounded-lg p-1.5 ui-text-muted ui-hover-soft"
              aria-label={currentPreviewPath?.startsWith("browser://") ? "关闭云端浏览器" : "打开云端浏览器"}
              title={currentPreviewPath?.startsWith("browser://") ? "关闭云端浏览器" : "打开云端浏览器"}
            >
                <Globe
                  size={18}
                  strokeWidth={currentPreviewPath?.startsWith("browser://") ? 2.25 : 1.75}
                  className={currentPreviewPath?.startsWith("browser://") ? "text-[var(--accent)]" : ""}
                />
            </button>
            <button
              type="button"
              onClick={() => void loadSkills()}
              className="inline-flex items-center justify-center rounded-lg p-2 ui-text-muted ui-hover-soft"
              aria-label="刷新技能列表"
              title="刷新技能列表"
            >
              <RefreshCw size={18} strokeWidth={2} className={skillsLoading ? "animate-spin" : ""} aria-hidden />
            </button>
          </div>
        </summary>

        {skillsError && (
          <p className="text-[10px] text-[var(--danger)] px-1">
            {skillsError}
          </p>
        )}
        {skillPublishStatus && (
          <p className="text-[10px] ui-text-secondary px-1">
            {skillPublishStatus}
          </p>
        )}
        {skillPublishError && (
          <p className="text-[10px] text-[var(--danger)] px-1">
            {skillPublishError}
          </p>
        )}

          <div className="max-h-48 overflow-y-auto overflow-x-hidden space-y-0 [scrollbar-width:thin]" role="list">
          {!skillsLoading && skills.length === 0 && (
            <p className="text-[10px] text-[var(--text-muted)]/70">暂无技能。</p>
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
                  "relative rounded-lg border border-transparent ui-motion-fast group overflow-hidden " +
                  (isActive
                    ? "bg-[var(--surface-1)]"
                    : "ui-hover-soft")
                }
              >
                {isActive ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-[var(--accent)]"
                  />
                ) : null}
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
                  className="w-full text-left pl-3 pr-6 py-2 text-sm font-medium ui-text-primary group-hover:pr-28 flex items-center gap-1.5 min-w-0 transition-[padding]"
                >
                  <span className="truncate">{s.name}</span>
                  {s.source === "remote-imported" ? (
                    <span className="shrink-0 rounded px-1 py-0.5 text-[10px] font-medium leading-none border border-[var(--border-subtle)] ui-text-secondary tracking-[0.12em] uppercase">
                      remote
                    </span>
                  ) : (
                    <span className="shrink-0 rounded px-1 py-0.5 text-[10px] font-medium leading-none ui-text-muted border border-[var(--border-subtle)] tracking-[0.12em] uppercase">
                      local
                    </span>
                  )}
                </button>
                {/* 悬浮操作组：上传/回收 / 复制路径 / 打开位置 —— 键盘 focus 也能显示 */}
                <div className="absolute right-1 top-0 bottom-0 flex items-center gap-0.5 pr-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 ui-motion-fast">
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
                    className="rounded px-1.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] ui-text-muted ui-hover-soft"
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
                      ? <Check size={18} strokeWidth={2.25} style={{ color: "var(--accent)" }} />
                      : <Copy size={18} />}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleOpenLocation(s.skillFile)}
                    className="ui-btn-ghost rounded p-1"
                    aria-label={`打开位置 ${s.name}`}
                    title="打开所在位置"
                  >
                    <FolderOpen size={18} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

            </details>

            {/* ── SidebarSecondary §组织资产：默认折叠 ── */}
            <details className="group/details flex flex-col gap-2 min-h-0 rounded-xl border border-[var(--border-subtle)] bg-white/[0.03] p-3 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-md px-1 py-1 ui-hover-soft">
                <span className="flex items-center gap-1.5 min-w-0">
                  <ChevronRight size={12} strokeWidth={2.25} className="shrink-0 ui-text-muted ui-motion-fast group-open/details:rotate-90" aria-hidden />
                  <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>组织资产</span>
                  <span className="ml-1 tabular-nums text-[10px] ui-text-secondary">{orgAssets.length}</span>
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    void loadOrgAssets();
                  }}
                  className="inline-flex items-center justify-center rounded-lg p-1.5 ui-text-muted ui-hover-soft"
                  aria-label="刷新组织资产"
                  title="刷新组织资产"
                >
                  <RefreshCw size={16} strokeWidth={2} className={orgAssetsLoading ? "animate-spin" : ""} aria-hidden />
                </button>
              </summary>
        {!orgAssetsConnected ? (
          <div className="flex flex-col items-center justify-center gap-2 py-3">
            <span className="text-lg opacity-70" aria-hidden="true">
              🏛️
            </span>
            <p className="text-[10px] ui-text-muted text-center leading-snug px-2">
              未连接组织中心
            </p>
            <button
              type="button"
              onClick={onOpenSettings}
              className="text-[10px] font-medium ui-text-muted hover:text-[var(--text-primary)] underline-offset-4 hover:underline ui-motion-fast py-1"
            >
              去连接
            </button>
          </div>
        ) : orgAssetsError ? (
          <p className="text-[10px] text-[var(--danger)] px-1">
            {orgAssetsError}
          </p>
        ) : (
          <div className="max-h-48 overflow-y-auto overflow-x-hidden space-y-2 [scrollbar-width:thin]">
            {!orgAssetsLoading && orgAssets.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-1.5 py-3">
                <span className="text-lg opacity-60" aria-hidden="true">
                  🏛️
                </span>
                <p className="text-[10px] ui-text-muted text-center leading-snug px-2">暂无组织资产。</p>
              </div>
            ) : (
              orgAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="relative rounded-xl p-3 flex flex-col gap-2 ui-hover-soft border border-transparent"
                >
                  <div className="min-w-0">
                    <p className="text-[12px] font-medium ui-text-primary truncate">{asset.title || asset.name}</p>
                    <p className="text-[10px] ui-text-muted mt-1 line-clamp-2">{asset.description || asset.organizationName || "组织资产"}</p>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] opacity-50 ui-text-secondary">v{asset.version || "未标注"}</span>
                    <button
                      type="button"
                      onClick={() => onOpenOrgAssetDetail?.(asset.id)}
                      className="rounded-lg px-2 py-1 text-[10px] font-medium uppercase tracking-[0.12em] ui-text-muted ui-hover-soft"
                    >
                      查看详情
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
            </details>
          </div>
        </div>

        {/* ── SidebarFooter：仅设置入口（破坏性 Logout 已移入 Settings 内） ── */}
        {onOpenQuickSettings ? (
          <div className="mt-3 flex shrink-0 flex-col gap-2 pt-3 border-t border-[var(--border-subtle)]">
            <button type="button" onClick={onOpenQuickSettings} className={settingsBtnClass} title="设置">
              <Settings size={18} className="shrink-0 opacity-90" />
              <span className="min-w-0 truncate">设置</span>
            </button>
          </div>
        ) : null}
      </aside>

      {portalTrashModal}
      {portalSkillModal}

      {hoveredSkill?.description && tooltipPos && (
        <div
          className="pointer-events-none fixed z-[9999] w-56 rounded-lg px-3 py-2 text-[10px] leading-snug shadow-xl animate-in fade-in duration-100"
          style={{
            top: tooltipPos.top,
            left: tooltipPos.left,
            background: "var(--surface-1)",
            border: "1px solid var(--border-subtle)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
          }}
          aria-hidden="true"
        >
          <p className="font-semibold ui-text-primary mb-1 text-[10px]">{hoveredSkill.name}</p>
          <p className="ui-text-secondary leading-snug">{hoveredSkill.description}</p>
        </div>
      )}
    </>
  );
}
