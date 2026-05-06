"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SkillUiBootstrapEvent, SkillUiDataPatchEvent } from "@/hooks/useAgentChat";
import { ProjectOverview } from "@/components/dashboard/ProjectOverview";
import { ModuleDashboard } from "@/components/dashboard/ModuleDashboard";
import {
  selectProjectModule,
  selectProjectOverviewModules,
  useProjectOverviewStore,
} from "@/lib/projectOverviewStore";
import { canonicalModuleIdForMerge, moduleTabLabelFromId } from "@/lib/moduleDisplayLabels";

export type ModuleEntry = {
  moduleId: string;
  syntheticPath: string;
  label: string;
  description?: string;
  isPlaceholder?: boolean;
  progressPct?: number;
  progressLabel?: string;
  steps?: Array<{ id: string; name: string; done: boolean }>;
  status: "running" | "idle" | "completed";
};

type ModuleRow = { syntheticPath: string; label: string };

type Props = {
  threadId: string;
  activeModuleIds: ReadonlySet<string>;
  /** 本会话内收到的 SkillUiDataPatch 序列（勿仅用最后一项，否则高频 patch 会丢） */
  skillUiPatchQueue?: readonly SkillUiDataPatchEvent[] | null;
  skillUiBootstrapEvent: SkillUiBootstrapEvent | null | undefined;
  onOpenPreview: (path: string) => void;
  postToAgent: (text: string) => void | Promise<void>;
  postToAgentSilently?: (text: string) => void | Promise<void>;
  isAgentRunning: boolean;
  activeSkillName?: string | null;
  /** 总览 vs Skill 模块大盘切换（供外层控制顶栏/项目区等） */
  onViewChange?: (view: "overview" | "module") => void;
};

function extractModuleId(syntheticPath: string): string | null {
  const raw = String(syntheticPath || "");
  // Support both:
  // - skill-ui://SduiView?dataFile=/skills/<id>/data/dashboard.json
  // - skill-ui://SduiView?dataFile=skills/<id>/data/dashboard.json
  // - (fallback) any ".../skills/<id>/..." substring
  const m1 = raw.match(/(?:\?|&)dataFile=\/?skills\/([^/&?#]+)\//);
  if (m1?.[1]) return m1[1];
  const m2 = raw.match(/\/skills\/([^/]+)\//);
  return m2?.[1] ?? null;
}

/** 在收到 Patch 前仅有 moduleId 时，占位 dataFile（须含 `/skills/{id}/` 供 extractModuleId 与后续 Patch 对齐） */
function placeholderSyntheticPath(moduleId: string): string {
  return `skill-ui://SduiView?dataFile=skills/${moduleId}/data/dashboard.json`;
}

function activeModuleIdsMatchCanon(activeModuleIds: ReadonlySet<string>, canon: string): boolean {
  for (const id of activeModuleIds) {
    if (canonicalModuleIdForMerge(id) === canon) return true;
  }
  return false;
}

export function DashboardNavigator({
  threadId,
  activeModuleIds,
  skillUiPatchQueue,
  skillUiBootstrapEvent,
  onOpenPreview,
  postToAgent,
  postToAgentSilently,
  isAgentRunning,
  activeSkillName,
  onViewChange,
}: Props) {
  const latestSkillUiPatch = skillUiPatchQueue?.length ? skillUiPatchQueue[skillUiPatchQueue.length - 1] : null;
  const [view, setView] = useState<"overview" | "module">("overview");

  useEffect(() => {
    onViewChange?.(view);
  }, [view, onViewChange]);
  const [modules, setModules] = useState<Map<string, ModuleRow>>(new Map());
  const [visible, setVisible] = useState(true);
  const userOverrideRef = useRef(false);
  const prevActiveRef = useRef<ReadonlySet<string>>(new Set());
  /** 同一会话内对某 Skill 仅自动切入模块大盘一次（用户点「总览」后不再抢焦点） */
  const autoOpenedSkillRef = useRef<string | null>(null);
  const overviewModules = useProjectOverviewStore(selectProjectOverviewModules);
  const activeModuleId = useProjectOverviewStore((snapshot) => snapshot.activeModuleId);

  useEffect(() => {
    setModules(new Map());
    setView("overview");
    selectProjectModule(null);
    userOverrideRef.current = false;
    prevActiveRef.current = new Set();
    autoOpenedSkillRef.current = null;
  }, [threadId]);

  /** 侧栏选中 Skill 后立刻在大盘登记占位模块，避免在首轮 guide/Patch 前长时间空白 */
  useEffect(() => {
    const name = activeSkillName?.trim();
    if (!name) return;
    if (name === "nanobot_agent") return;
    const canon = canonicalModuleIdForMerge(name);
    setModules((prev) => {
      if (prev.has(canon)) return prev;
      const next = new Map(prev);
      next.set(canon, {
        syntheticPath: placeholderSyntheticPath(name),
        label: moduleTabLabelFromId(name),
      });
      return next;
    });
  }, [activeSkillName]);

  const fadeSwitch = useCallback((fn: () => void) => {
    setVisible(false);
    setTimeout(() => {
      fn();
      setVisible(true);
    }, 300);
  }, []);

  const switchToModule = useCallback(
    (moduleId: string, byUser: boolean) => {
      if (byUser) userOverrideRef.current = true;
      const raw = moduleId.trim();
      const canon = canonicalModuleIdForMerge(raw);
      setModules((prev) => {
        if (prev.has(canon)) return prev;
        const next = new Map(prev);
        next.set(canon, {
          syntheticPath: placeholderSyntheticPath(raw),
          label: moduleTabLabelFromId(raw),
        });
        return next;
      });
      fadeSwitch(() => {
        selectProjectModule(canon);
        setView("module");
      });
    },
    [fadeSwitch],
  );

  /** 收到大盘 Patch 时自动进入该模块的 Skill 视图（避免一直停在「项目总览」只看小卡片） */
  useEffect(() => {
    const ev = latestSkillUiPatch;
    if (!ev?.syntheticPath) return;
    const moduleId = extractModuleId(ev.syntheticPath);
    if (!moduleId) return;
    if (userOverrideRef.current) return;
    if (
      view === "module" &&
      activeModuleId &&
      canonicalModuleIdForMerge(activeModuleId) === canonicalModuleIdForMerge(moduleId)
    ) {
      return;
    }
    switchToModule(moduleId, false);
  }, [latestSkillUiPatch, view, activeModuleId, switchToModule]);

  /** 侧栏/会话已锁定模块且仍在总览时，自动打开对应模块大盘 */
  useEffect(() => {
    const name = activeSkillName?.trim();
    if (!name) return;
    if (name === "nanobot_agent") return;
    if (userOverrideRef.current) return;
    const canon = canonicalModuleIdForMerge(name);
    const knownByOverview = overviewModules.some(
      (item) => canonicalModuleIdForMerge(item.moduleId) === canon,
    );
    if (!modules.has(canon) && !knownByOverview) return;
    if (view !== "overview") return;
    if (autoOpenedSkillRef.current === canon) return;
    autoOpenedSkillRef.current = canon;
    switchToModule(name, false);
  }, [activeSkillName, modules, overviewModules, view, switchToModule]);

  // activeTaskModuleStatus kept for legacy auto-guide policy (disabled in skill-first option 1).

  // Skill-First (Option 1): platform MUST NOT auto-trigger any module flow.
  // Entry actions must be defined by the skill dashboard itself (e.g., skill_runtime_start).

  const switchToOverview = useCallback(() => {
    userOverrideRef.current = false;
    fadeSwitch(() => {
      selectProjectModule(null);
      setView("overview");
    });
  }, [fadeSwitch]);

  // Patch / Bootstrap：只登记 syntheticPath 与 label，不切 Tab（由 ModuleSessionFocus 驱动）
  useEffect(() => {
    const syntheticPath = latestSkillUiPatch?.syntheticPath ?? skillUiBootstrapEvent?.syntheticPath;
    if (!syntheticPath) return;
    const moduleId = extractModuleId(syntheticPath);
    if (!moduleId) return;
    const canon = canonicalModuleIdForMerge(moduleId);

    setModules((prev) => {
      const next = new Map(prev);
      for (const [k] of next.entries()) {
        if (k !== canon && canonicalModuleIdForMerge(k) === canon) next.delete(k);
      }
      const existing = next.get(canon);
      next.set(canon, {
        syntheticPath,
        label: existing?.label ?? moduleTabLabelFromId(moduleId),
      });
      return next;
    });
  }, [latestSkillUiPatch, skillUiBootstrapEvent]);

  // 焦点：补全未知模块占位、检测新增 id 并自动切 Tab
  useEffect(() => {
    setModules((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const id of activeModuleIds) {
        const canon = canonicalModuleIdForMerge(id);
        if (!next.has(canon)) {
          next.set(canon, {
            syntheticPath: placeholderSyntheticPath(id),
            label: moduleTabLabelFromId(id),
          });
          changed = true;
        }
      }
      return changed ? next : prev;
    });

    const prev = prevActiveRef.current;
    const added = [...activeModuleIds].filter((id) => !prev.has(canonicalModuleIdForMerge(id)));
    prevActiveRef.current = new Set([...activeModuleIds].map((id) => canonicalModuleIdForMerge(id)));

    if (added.length > 0 && !userOverrideRef.current) {
      const newId = added[added.length - 1]!;
      switchToModule(newId, false);
    }
  }, [activeModuleIds, switchToModule]);

  const moduleEntries: ModuleEntry[] = useMemo(() => {
    const merged = new Map<string, ModuleEntry>();
    for (const item of overviewModules) {
      const canon = canonicalModuleIdForMerge(item.moduleId);
      const dynamic = modules.get(canon);
      merged.set(canon, {
        moduleId: canon,
        syntheticPath: dynamic?.syntheticPath ?? item.syntheticPath,
        label: dynamic?.label ?? item.label,
        description: item.description,
        isPlaceholder: item.isPlaceholder,
        progressPct: item.progressPct,
        progressLabel: item.currentStepLabel,
        steps: item.steps,
        status: activeModuleIdsMatchCanon(activeModuleIds, canon) ? "running" : item.status,
      });
    }
    for (const [moduleId, row] of modules.entries()) {
      const canon = canonicalModuleIdForMerge(moduleId);
      if (merged.has(canon)) {
        const ex = merged.get(canon)!;
        let syntheticPath = ex.syntheticPath;
        if (
          !syntheticPath.includes("modeling_simulation_workbench") &&
          row.syntheticPath.includes("modeling_simulation_workbench")
        ) {
          syntheticPath = row.syntheticPath;
        }
        merged.set(canon, {
          ...ex,
          syntheticPath,
          label: ex.label || row.label,
        });
        continue;
      }
      merged.set(canon, {
        moduleId: canon,
        syntheticPath: row.syntheticPath,
        label: row.label,
        isPlaceholder: true,
        status: activeModuleIdsMatchCanon(activeModuleIds, canon) ? "running" : "idle",
      });
    }
    return [...merged.values()];
  }, [modules, overviewModules, activeModuleIds]);

  const activeEntry = activeModuleId
    ? moduleEntries.find((e) => e.moduleId === activeModuleId) ?? null
    : null;

  return (
    <div
      className="dashboard-density-viewport h-full min-h-0 flex flex-col transition-opacity duration-300"
      style={{ opacity: visible ? 1 : 0 }}
    >
      {view === "overview" ? (
        <ProjectOverview
          modules={moduleEntries}
          onSelectModule={(id) => switchToModule(id, true)}
        />
      ) : (
        <ModuleDashboard
          entry={activeEntry}
          allModules={moduleEntries}
          onSelectModule={(id) => switchToModule(id, true)}
          onBack={switchToOverview}
          skillUiPatchQueue={skillUiPatchQueue ?? []}
          onOpenPreview={onOpenPreview}
          postToAgent={postToAgent}
          postToAgentSilently={postToAgentSilently}
          isAgentRunning={isAgentRunning}
          activeSkillName={activeSkillName}
        />
      )}
    </div>
  );
}
