"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Check, Copy, FileText, FolderOpen, Globe, RefreshCw, Settings, Trash2 } from "lucide-react";
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
  sessions: SessionSummary[];
  onCreateSession: () => void;
  onSelectSession: (threadId: string) => void;
  onDeleteSession?: (threadId: string) => void;
  onOpenSettings?: () => void;
  onSkillSelect?: (skillName: string) => void;
};

type SkillItem = {
  name: string;
  skillDir: string;
  skillFile: string;
  mtimeMs: number;
};

type SkillsResp = { items: SkillItem[] };
type TrashModalState = { open: boolean; mode: "one" | "all"; targets: string[] };

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
  sessions,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  onOpenSettings,
  onSkillSelect,
}: Props) {
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
  const [removedPaths, setRemovedPaths] = useState<Set<string>>(new Set());
  const [trashError, setTrashError] = useState<string | null>(null);
  const [trashBusy, setTrashBusy] = useState(false);
  const [trashModal, setTrashModal] = useState<TrashModalState>({ open: false, mode: "one", targets: [] });
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const artifacts = useMemo(() => {
    const all = extractIndexedFiles(messages);
    return all.filter((f) => !removedPaths.has(f.path));
  }, [messages, removedPaths]);

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
  }, [loadSkills]);

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

  return (
    <aside className="ui-panel h-full min-h-0 overflow-y-auto rounded-2xl p-4 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Bot size={16} className="ui-text-secondary shrink-0" />
        <span className="font-semibold text-sm ui-text-primary">Nanobot AGUI</span>
        <span className="ml-auto w-2 h-2 rounded-full" style={{ background: "var(--success)" }} title="已连接" />
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

      <section className="ui-card rounded-xl p-3 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
            产物 <span className="font-normal normal-case tracking-normal ui-text-muted">Artifacts</span>
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

        <div className="max-h-48 overflow-auto space-y-0.5">
          {artifacts.length === 0 ? (
            <p className="text-[11px] ui-text-muted">本轮生成的文件会出现在这里，点击后统一在右侧预览。</p>
          ) : (
            artifacts.map((artifact, index) => (
              <div key={artifact.path} className="flex items-center gap-1 rounded-lg px-2 py-1.5 hover:bg-[var(--surface-3)] transition-colors group">
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

      <section className="ui-card rounded-xl p-3 flex flex-col gap-2 min-h-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
            技能 <span className="font-normal normal-case tracking-normal ui-text-muted">Skills</span>
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

        <div className="max-h-44 overflow-auto space-y-0.5" role="list">
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
                className={
                  "relative rounded-lg border transition-colors group " +
                  (isActive
                    ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                    : "border-[var(--border-subtle)] bg-[var(--surface-3)] hover:border-[var(--border-strong)]")
                }
              >
                <button
                  type="button"
                  onClick={() => {
                    if (currentPreviewPath === s.skillFile) {
                      setSelectedSkillName(null);
                      onClosePreview?.();
                    } else {
                      setSelectedSkillName(s.name);
                      onPreviewPath(s.skillFile);
                      onSkillSelect?.(s.name);
                    }
                  }}
                  className="w-full text-left px-2.5 py-2 text-sm ui-text-secondary pr-16"
                  title={s.skillDir}
                >
                  {s.name}
                </button>
                {/* 悬浮操作组：复制路径 / 打开位置 */}
                <div className="absolute right-1 top-0 bottom-0 flex items-center gap-0.5 pr-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
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

      {trashModal.open && (
        <div className="ui-card rounded-xl p-3 text-xs space-y-2" style={{ borderColor: "rgba(247,184,75,0.28)", background: "rgba(247,184,75,0.08)" }}>
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

      {/* ── Bottom control bar ── */}
      <div
        className="mt-auto -mx-4 px-3 pt-3 pb-1 flex items-center gap-1"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
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
      </div>
    </aside>
  );
}
