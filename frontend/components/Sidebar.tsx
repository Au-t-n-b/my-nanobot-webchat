"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Building2, Check, ChevronRight, Copy, FileText, FolderOpen, Globe, LogOut, Plus, RefreshCw, Settings, Trash2, Zap } from "lucide-react";
import { CenteredConfirmModal, CenteredModal } from "@/components/CenteredModal";
import { SessionList } from "@/components/SessionList";
import type { AgentMessage, SessionSummary } from "@/hooks/useAgentChat";
import { extractIndexedFiles } from "@/lib/fileIndex";
import { openLocation } from "@/lib/apiFile";
import { SIDEBAR_SECTION_LABEL_CLASS } from "@/lib/sidebarTokens";
import {
  createLocalProjectWithMeta,
  ensureAtLeastOneLocalProject,
  listLocalProjects,
  setSelectedLocalProjectId,
  type LocalProject,
} from "@/lib/localProjects";

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
  /** Opens quick settings (e.g. control center settings tab). */
  onOpenQuickSettings?: () => void;
  /** Local demo auth: sign out and return to login. */
  onLogout?: () => void;
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

type ProjectScenarioPreset = "" | "风冷" | "液冷" | "混合" | "其他";
function asScenarioPreset(v: string): ProjectScenarioPreset {
  const t = v.trim();
  if (t === "风冷" || t === "液冷" || t === "混合" || t === "其他") return t;
  return "";
}

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
  onOpenQuickSettings,
  onLogout,
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
  const [projects, setProjects] = useState<LocalProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [projectCreateOpen, setProjectCreateOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectCode, setNewProjectCode] = useState("");
  const [newProjectBidCode, setNewProjectBidCode] = useState("");
  const [newProjectScenario, setNewProjectScenario] = useState("");
  const [newProjectScenarioPreset, setNewProjectScenarioPreset] = useState<ProjectScenarioPreset>("");
  const [newProjectScenarioDetail, setNewProjectScenarioDetail] = useState("");
  const [newProjectScale, setNewProjectScale] = useState("");
  const [newProjectDeliveryFeatures, setNewProjectDeliveryFeatures] = useState("");
  const [newProjectLanguage, setNewProjectLanguage] = useState("");
  const [newProjectGroup, setNewProjectGroup] = useState("");
  const [newProjectStakeholders, setNewProjectStakeholders] = useState("");
  const [projectMetaOpen, setProjectMetaOpen] = useState(false);
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

  useEffect(() => {
    const { projects, selectedId } = ensureAtLeastOneLocalProject();
    setProjects(projects);
    setSelectedProjectId(selectedId);
  }, []);

  const copyPath = useCallback((path: string) => {
    void navigator.clipboard.writeText(path).then(() => {
      setCopiedPath(path);
      setTimeout(() => setCopiedPath(null), 1400);
    });
  }, []);

  const refreshProjects = useCallback(() => {
    const next = listLocalProjects();
    setProjects(next);
    setSelectedProjectId((cur) => {
      if (cur && next.some((p) => p.id === cur)) return cur;
      const fallback = next[0]?.id ?? "";
      if (fallback) setSelectedLocalProjectId(fallback);
      return fallback;
    });
  }, []);

  const selectedProjectName = useMemo(() => {
    const p = projects.find((x) => x.id === selectedProjectId);
    return p?.name ?? "未选择项目";
  }, [projects, selectedProjectId]);

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
    const iconBtn =
      "rounded-lg p-2 text-zinc-500 hover:bg-zinc-900/40 hover:text-zinc-200 transition-colors w-10 h-10 flex items-center justify-center";
    return (
      <aside className="flex h-full min-h-0 flex-col items-center gap-1 overflow-hidden rounded-2xl bg-zinc-100 py-3 shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:bg-[#121214] dark:ring-white/10">
        <span className="text-lg leading-none mb-0.5" aria-hidden="true">
          🦞
        </span>
        <span className="mb-2 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--success)" }} title="已连接" />

        <button type="button" onClick={onCreateSession} title="新建会话" className={iconBtn}>
          <Plus size={18} />
        </button>

        <div className="relative" title={`产物 (${artifacts.length})，点击展开`}>
          <button type="button" onClick={onToggleCollapse} className={iconBtn}>
            <FileText size={18} />
          </button>
          {artifacts.length > 0 && (
            <span
              className="pointer-events-none absolute right-1 top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full text-[8px] font-bold text-white"
              style={{ background: "var(--accent)" }}
            >
              {artifacts.length > 9 ? "9+" : artifacts.length}
            </span>
          )}
        </div>

        <button type="button" title="技能，点击展开" onClick={onToggleCollapse} className={iconBtn}>
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
    "w-full min-w-0 inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-200/80 bg-white/40 px-3 py-2.5 text-sm font-medium text-zinc-700 shadow-sm transition-colors hover:bg-white/70 dark:border-white/10 dark:bg-zinc-900/40 dark:text-zinc-100 dark:hover:bg-zinc-900/70";

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
      <div className="space-y-3 text-xs">
        <p className="ui-text-muted break-all">{skillPublishModal.skill.name}</p>
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
        {skillPublishError ? (
          <p className="rounded-lg px-2 py-1" style={{ background: "rgba(239,107,115,0.12)", color: "var(--danger)" }}>
            {skillPublishError}
          </p>
        ) : null}
        <div className="flex gap-2 pt-1">
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
    </CenteredModal>
  ) : null;

  return (
    <>
      <aside className="flex h-full min-h-0 flex-col gap-0 overflow-hidden rounded-2xl bg-zinc-100 pl-4 pt-4 pb-4 pr-1.5 shadow-[var(--shadow-card)] ring-1 ring-black/[0.05] dark:bg-[#121214] dark:ring-white/10">
        <div className="flex shrink-0 items-center gap-2.5 min-w-0 px-0 pr-1.5">
          <span className="text-xl leading-none shrink-0 select-none" aria-hidden="true">
            🦞
          </span>
          <span className="min-w-0 flex-1 truncate font-semibold text-base leading-tight tracking-tight ui-text-primary">
            AI应用使能 <span className="text-[var(--accent)]">交付claw</span>
          </span>
          <span className="ml-auto h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: "var(--success)" }} title="已连接" />
        </div>

        <div className="min-h-0 flex-1 touch-pan-y overflow-y-auto overflow-x-hidden pr-0 [overscroll-behavior-y:auto]">
          <div className="flex flex-col gap-3 pb-2 pt-3 pr-1.5">
            <section className="rounded-xl border border-[var(--border-subtle)] bg-white/40 dark:bg-black/10 px-3 py-2 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)]">
              <div className="flex items-center justify-between gap-2">
                <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>当前项目</span>
                <button
                  type="button"
                  onClick={() => {
                    setNewProjectName("");
                    setNewProjectCode("");
                    setNewProjectBidCode("");
                    setNewProjectScenario("");
                    setNewProjectScenarioPreset("");
                    setNewProjectScenarioDetail("");
                    setNewProjectScale("");
                    setNewProjectDeliveryFeatures("");
                    setNewProjectLanguage("");
                    setNewProjectGroup("");
                    setNewProjectStakeholders("");
                    setProjectMetaOpen(false);
                    setProjectCreateOpen(true);
                  }}
                  className="inline-flex items-center justify-center rounded-lg p-1.5 text-zinc-500 transition-colors hover:bg-zinc-900/40 hover:text-zinc-200"
                  aria-label="新建项目"
                  title="新建项目"
                >
                  <Plus size={18} strokeWidth={2} aria-hidden />
                </button>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <select
                  value={selectedProjectId}
                  onChange={(e) => {
                    const id = e.target.value;
                    setSelectedProjectId(id);
                    setSelectedLocalProjectId(id);
                  }}
                  className="ui-input ui-input-focusable w-full rounded-lg px-2.5 py-2 text-xs"
                  aria-label="选择项目"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <p className="mt-1 text-[10px] ui-text-muted truncate" title={selectedProjectName}>{selectedProjectName}</p>
            </section>

            <SessionList
              currentThreadId={threadId}
              sessions={sessions}
              onCreate={onCreateSession}
              onSelect={onSelectSession}
              onDelete={onDeleteSession}
            />

            <section className="flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>Artifacts</span>
          <button
            type="button"
            disabled={artifacts.length === 0}
            onClick={() => {
              setTrashError(null);
              setTrashModal({ open: true, mode: "all", targets: artifacts.map((f) => f.path) });
            }}
            className="inline-flex items-center justify-center rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-900/40 hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="清空最近产物并移入回收站"
            title="清空最近产物"
          >
            <Trash2 size={20} strokeWidth={2} aria-hidden />
          </button>
        </div>

        <div className="max-h-[200px] overflow-y-auto overflow-x-hidden space-y-0.5">
          {artifacts.length === 0 ? (
            <p className="text-[11px] text-zinc-500/70">本轮生成的文件会出现在这里，点击后统一在右侧预览。</p>
          ) : (
            artifacts.map((artifact, index) => (
              <div
                key={artifact.path}
                className={
                  "group relative flex items-center gap-1 rounded-md pl-3 pr-2 py-1.5 transition-colors " +
                  (currentPreviewPath === artifact.path ? "bg-zinc-900" : "hover:bg-zinc-900/40")
                }
              >
                {currentPreviewPath === artifact.path ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.4)] rounded-r"
                  />
                ) : null}
                <button
                  type="button"
                  onClick={() => togglePreview(artifact.path)}
                  className="flex-1 text-left flex items-center gap-1.5 min-w-0"
                  title={artifact.path}
                >
                  <FileText size={18} strokeWidth={currentPreviewPath === artifact.path ? 2.25 : 1.75} className="text-zinc-500 shrink-0" />
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
                      ? <Check size={18} strokeWidth={2.25} style={{ color: "var(--success)" }} />
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
      </section>

            <section className="flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>Skills</span>
          <div className="flex items-center gap-1">
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
              className="inline-flex items-center rounded-lg p-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900/40 transition-colors"
              aria-label={currentPreviewPath?.startsWith("browser://") ? "关闭云端浏览器" : "打开云端浏览器"}
              title={currentPreviewPath?.startsWith("browser://") ? "关闭云端浏览器" : "打开云端浏览器"}
            >
              <Globe size={18} strokeWidth={currentPreviewPath?.startsWith("browser://") ? 2.25 : 1.75} className={currentPreviewPath?.startsWith("browser://") ? "text-blue-400" : ""} />
            </button>
            <button
              type="button"
              onClick={() => void loadSkills()}
              className="inline-flex items-center justify-center rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-900/40 hover:text-zinc-200"
              aria-label="刷新技能列表"
              title="刷新技能列表"
            >
              <RefreshCw size={20} strokeWidth={2} className={skillsLoading ? "animate-spin" : ""} aria-hidden />
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
            <p className="text-[11px] text-zinc-500/70">暂无技能（已自动创建 skills 目录）。</p>
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
                  "relative rounded-md border border-transparent transition-colors group overflow-hidden " +
                  (isActive
                    ? "bg-zinc-900"
                    : "hover:bg-zinc-900/40")
                }
              >
                {isActive ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1 bottom-1 w-[2px] bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.4)] rounded-r"
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
                    className="rounded px-1.5 py-1 text-[11px] font-bold uppercase tracking-wide text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900/40 transition-colors"
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
                      ? <Check size={18} strokeWidth={2.25} style={{ color: "var(--success)" }} />
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

            </section>

            {/* ── 组织资产 Organization Assets（幽灵卡片，降低视觉重量）── */}
            <section className="flex flex-col gap-2 min-h-0 rounded-xl border border-dashed border-zinc-400/55 dark:border-white/15 bg-white/[0.04] dark:bg-white/[0.03] p-3">
        <div className="flex items-center justify-between gap-2">
          <span className={`${SIDEBAR_SECTION_LABEL_CLASS} whitespace-nowrap`}>Org Assets</span>
          <button
            type="button"
            onClick={() => void loadOrgAssets()}
            className="inline-flex items-center justify-center rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-900/40 hover:text-zinc-200"
            aria-label="刷新组织资产"
            title="刷新组织资产"
          >
            <RefreshCw size={20} strokeWidth={2} className={orgAssetsLoading ? "animate-spin" : ""} aria-hidden />
          </button>
        </div>
        {!orgAssetsConnected ? (
          <div className="flex flex-col items-center justify-center gap-2 py-3 rounded-lg border border-zinc-300/60 dark:border-white/12 bg-zinc-50/30 dark:bg-transparent">
            <span className="text-lg opacity-70" aria-hidden="true">
              🏛️
            </span>
            <p className="text-[11px] text-zinc-600 dark:text-zinc-300 text-center leading-relaxed px-2">
              远端组织资产未连接
              <br />
              <span className="text-[10px] text-zinc-400 dark:text-zinc-500">请先在设置中登录组织中心</span>
            </p>
            <button
              type="button"
              onClick={onOpenSettings}
              className="text-[11px] font-medium text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200 underline-offset-4 hover:underline transition-colors py-1"
            >
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
              <div className="flex flex-col items-center justify-center gap-1.5 py-3 rounded-lg border border-dashed border-zinc-200/40 dark:border-white/[0.08] bg-transparent">
                <span className="text-lg opacity-60" aria-hidden="true">
                  🏛️
                </span>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400 text-center leading-relaxed px-2">
                  当前没有可展示的组织资产。
                </p>
              </div>
            ) : (
              orgAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="relative rounded-lg p-2.5 flex flex-col gap-2 transition-colors hover:bg-zinc-900/40 border border-transparent"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-medium ui-text-primary truncate">{asset.title || asset.name}</p>
                    <p className="text-[11px] ui-text-muted mt-1 line-clamp-2">{asset.description || asset.organizationName || "组织资产"}</p>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[9px] opacity-40 text-zinc-200">v{asset.version || "未标注"}</span>
                    <button
                      type="button"
                      onClick={() => onOpenOrgAssetDetail?.(asset.id)}
                      className="rounded-lg px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900/40 transition-colors"
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
          </div>
        </div>

        {(onOpenQuickSettings || onLogout) && (
          <div className="mt-2 flex shrink-0 flex-col gap-2 pr-1.5 pt-1">
            {onOpenQuickSettings ? (
              <button type="button" onClick={onOpenQuickSettings} className={settingsBtnClass} title="设置">
                <Settings size={18} className="shrink-0 opacity-90" />
                <span className="min-w-0 truncate">设置</span>
              </button>
            ) : null}
            {onLogout ? (
              <button
                type="button"
                onClick={onLogout}
                className={`${settingsBtnClass} border-red-200/50 text-red-700 hover:bg-red-50 dark:border-red-900/40 dark:text-red-300 dark:hover:bg-red-950/40`}
                title="退出登录"
              >
                <LogOut size={18} className="shrink-0 opacity-90" />
                <span className="min-w-0 truncate">退出登录</span>
              </button>
            ) : null}
          </div>
        )}
      </aside>

      {portalTrashModal}
      {portalSkillModal}

      <CenteredModal
        open={projectCreateOpen}
        onClose={() => setProjectCreateOpen(false)}
        title="新建项目"
        panelClassName="w-full max-w-md"
        footer={(
          <div className="flex justify-end gap-2">
            <button type="button" className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs font-medium" onClick={() => setProjectCreateOpen(false)}>
              取消
            </button>
            <button
              type="button"
              className="ui-btn-accent rounded-lg px-3 py-1.5 text-xs font-medium"
              onClick={() => {
                const scenario =
                  newProjectScenarioPreset && newProjectScenarioPreset !== "其他"
                    ? (newProjectScenarioDetail.trim()
                        ? `${newProjectScenarioPreset}：${newProjectScenarioDetail.trim()}`
                        : newProjectScenarioPreset)
                    : (newProjectScenario.trim() || newProjectScenarioDetail.trim());
                const p = createLocalProjectWithMeta({
                  name: newProjectName,
                  code: newProjectCode,
                  bidCode: newProjectBidCode,
                  scenario,
                  scale: newProjectScale,
                  deliveryFeatures: newProjectDeliveryFeatures,
                  language: newProjectLanguage,
                  projectGroup: newProjectGroup,
                  stakeholders: newProjectStakeholders,
                });
                setProjectCreateOpen(false);
                setNewProjectName("");
                refreshProjects();
                setSelectedProjectId(p.id);
              }}
            >
              创建
            </button>
          </div>
        )}
      >
        <div className="space-y-2">
          <label className="block text-xs font-medium ui-text-secondary">项目名称</label>
          <input
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            placeholder="例如：宁波电网智慧工勘"
            className="ui-input ui-input-focusable w-full rounded-xl px-4 py-3 text-sm"
            autoFocus
          />
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setProjectMetaOpen((v) => !v)}
              className="text-[11px] ui-text-muted hover:ui-text-primary underline-offset-4 hover:underline"
            >
              {projectMetaOpen ? "收起更多项目信息" : "填写更多项目信息（可选）"}
            </button>
          </div>

          {projectMetaOpen ? (
            <div className="grid grid-cols-1 gap-3 pt-2">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] ui-text-muted mb-1">项目编码</label>
                  <input
                    value={newProjectCode}
                    onChange={(e) => setNewProjectCode(e.target.value)}
                    placeholder="例如：NB-DW-001"
                    className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] ui-text-muted mb-1">投标编码</label>
                  <input
                    value={newProjectBidCode}
                    onChange={(e) => setNewProjectBidCode(e.target.value)}
                    placeholder="例如：TB-2026-xx"
                    className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] ui-text-muted mb-1">场景</label>
                  <select
                    value={newProjectScenarioPreset}
                    onChange={(e) => setNewProjectScenarioPreset(asScenarioPreset(e.target.value))}
                    className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                    aria-label="选择项目场景"
                  >
                    <option value="">（可选）请选择</option>
                    <option value="风冷">风冷</option>
                    <option value="液冷">液冷</option>
                    <option value="混合">混合</option>
                    <option value="其他">其他</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] ui-text-muted mb-1">规模</label>
                  <input
                    value={newProjectScale}
                    onChange={(e) => setNewProjectScale(e.target.value)}
                    placeholder="如：省级/地市级/xx 条线路"
                    className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] ui-text-muted mb-1">场景补充（可选）</label>
                <input
                  value={newProjectScenarioPreset === "其他" ? newProjectScenario : newProjectScenarioDetail}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (newProjectScenarioPreset === "其他") setNewProjectScenario(v);
                    else setNewProjectScenarioDetail(v);
                  }}
                  placeholder={newProjectScenarioPreset === "其他" ? "如：智慧工勘/建模仿真/…（自由填写）" : "如：分区、机房类型、约束等"}
                  className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                />
              </div>

              <div>
                <label className="block text-[11px] ui-text-muted mb-1">交付特点</label>
                <input
                  value={newProjectDeliveryFeatures}
                  onChange={(e) => setNewProjectDeliveryFeatures(e.target.value)}
                  placeholder="如：多端联动/现场闭环/高安全要求"
                  className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] ui-text-muted mb-1">语言</label>
                  <input
                    value={newProjectLanguage}
                    onChange={(e) => setNewProjectLanguage(e.target.value)}
                    placeholder="如：中文/中英双语"
                    className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] ui-text-muted mb-1">项目群</label>
                  <input
                    value={newProjectGroup}
                    onChange={(e) => setNewProjectGroup(e.target.value)}
                    placeholder="如：电网数字化一期"
                    className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] ui-text-muted mb-1">相关人</label>
                <input
                  value={newProjectStakeholders}
                  onChange={(e) => setNewProjectStakeholders(e.target.value)}
                  placeholder="如：甲方张三/实施李四/监理王五"
                  className="ui-input ui-input-focusable w-full rounded-lg px-3 py-2 text-xs"
                />
              </div>
            </div>
          ) : null}

          <p className="pt-1 text-[11px] ui-text-muted">项目用于区分工作区上下文（本地演示，仅存于浏览器）。</p>
        </div>
      </CenteredModal>

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
    </>
  );
}
