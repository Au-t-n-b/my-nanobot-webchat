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

/** 六阶段标准 ID + 已知 chat-only skill 的中文显示名。
 *
 * 与 ``frontend/lib/projectOverviewRegistry.js`` 的 ``CANONICAL_SIX`` 一致；
 * 多录入两个 alias（``smart_survey`` / ``modeling_simulation_workbench``）以覆盖
 * 后端 driver 与 ``task_progress.json`` 中可能并存的两套 moduleId 写法。
 *
 * 该表只用于 tab 显示名的兜底，**不**改变路由 / 分发 / 文件路径里的 moduleId。
 */
const KNOWN_MODULE_LABELS: Record<string, string> = {
  job_management: "作业管理",
  smart_survey_workbench: "智慧工勘",
  smart_survey: "智慧工勘",
  jmfz: "建模仿真",
  modeling_simulation_workbench: "建模仿真",
  system_design: "系统设计",
  device_install: "设备安装",
  sw_deploy_commission: "软件部署与调测",
  project_guide: "项目引导",
};

function moduleLabel(id: string): string {
  const known = KNOWN_MODULE_LABELS[id];
  if (known) return known;
  return id.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Chat-only skills：这些 skill 仅经左侧 chat 卡片输出（如 ``project_guide`` 的 GuidanceCard），
 * 不应在右侧 DashboardNavigator 注册成 panel tab，否则会出现一个空壳 module（白屏）。
 *
 * 后端 ``skill_runtime_bridge._NON_PANEL_SKILL_NAMES`` 已经避免了 ``ModuleSessionFocus``
 * 抢焦点；前端这层是兜底：``activeSkillName`` / Patch / Bootstrap 三条 useEffect 都不应把
 * 这些 skill 写进本地 ``modules`` map。
 */
const CHAT_ONLY_SKILL_IDS: ReadonlySet<string> = new Set(["project_guide"]);

function isChatOnlySkill(id: string | null | undefined): boolean {
  if (!id) return false;
  return CHAT_ONLY_SKILL_IDS.has(id.trim());
}

/** 在收到 Patch 前仅有 moduleId 时，占位 dataFile（须含 `/skills/{id}/` 供 extractModuleId 与后续 Patch 对齐） */
function placeholderSyntheticPath(moduleId: string): string {
  return `skill-ui://SduiView?dataFile=skills/${moduleId}/data/dashboard.json`;
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
    // Chat-only skills（如 ``project_guide``）只在左侧 chat 出引导卡，不应该出现在右侧 panel tab。
    if (isChatOnlySkill(name)) return;
    setModules((prev) => {
      if (prev.has(name)) return prev;
      const next = new Map(prev);
      next.set(name, {
        syntheticPath: placeholderSyntheticPath(name),
        label: moduleLabel(name),
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
      setModules((prev) => {
        if (prev.has(moduleId)) return prev;
        const next = new Map(prev);
        next.set(moduleId, {
          syntheticPath: placeholderSyntheticPath(moduleId),
          label: moduleLabel(moduleId),
        });
        return next;
      });
      fadeSwitch(() => {
        selectProjectModule(moduleId);
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
    if (view === "module" && activeModuleId === moduleId) return;
    switchToModule(moduleId, false);
  }, [latestSkillUiPatch, view, activeModuleId, switchToModule]);

  /** 侧栏/会话已锁定模块且仍在总览时，自动打开对应模块大盘 */
  useEffect(() => {
    const name = activeSkillName?.trim();
    if (!name) return;
    if (name === "nanobot_agent") return;
    // Chat-only skills 不抢右侧大盘焦点。
    if (isChatOnlySkill(name)) return;
    if (userOverrideRef.current) return;
    const knownByOverview = overviewModules.some((item) => item.moduleId === name);
    if (!modules.has(name) && !knownByOverview) return;
    if (view !== "overview") return;
    if (autoOpenedSkillRef.current === name) return;
    autoOpenedSkillRef.current = name;
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
    // 防御性兜底：chat-only skill 不应该有 dashboard patch / bootstrap，但若上游误发也不要登记。
    if (isChatOnlySkill(moduleId)) return;

    setModules((prev) => {
      const next = new Map(prev);
      const existing = next.get(moduleId);
      next.set(moduleId, {
        syntheticPath,
        label: existing?.label ?? moduleLabel(moduleId),
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
        if (isChatOnlySkill(id)) continue;
        if (!next.has(id)) {
          next.set(id, {
            syntheticPath: placeholderSyntheticPath(id),
            label: moduleLabel(id),
          });
          changed = true;
        }
      }
      return changed ? next : prev;
    });

    const prev = prevActiveRef.current;
    const added = [...activeModuleIds].filter((id) => !prev.has(id) && !isChatOnlySkill(id));
    prevActiveRef.current = new Set(activeModuleIds);

    if (added.length > 0 && !userOverrideRef.current) {
      const newId = added[added.length - 1]!;
      switchToModule(newId, false);
    }
  }, [activeModuleIds, switchToModule]);

  const moduleEntries: ModuleEntry[] = useMemo(() => {
    const merged = new Map<string, ModuleEntry>();
    for (const item of overviewModules) {
      if (isChatOnlySkill(item.moduleId)) continue;
      const dynamic = modules.get(item.moduleId);
      // Overview 主导名：``item.label`` 来自 ``CANONICAL_SIX``（中文），动态注册的 ``dynamic.label``
      // 可能因为 ``moduleLabel(id)`` 的 fallback 退化成英文（"Job Management"）。这里**优先**取
      // overview 的中文 label，只有当 overview 里没有时才用 dynamic 的 fallback。
      merged.set(item.moduleId, {
        moduleId: item.moduleId,
        syntheticPath: dynamic?.syntheticPath ?? item.syntheticPath,
        label: item.label || dynamic?.label || moduleLabel(item.moduleId),
        description: item.description,
        isPlaceholder: item.isPlaceholder,
        progressPct: item.progressPct,
        progressLabel: item.currentStepLabel,
        steps: item.steps,
        status: activeModuleIds.has(item.moduleId) ? "running" : item.status,
      });
    }
    for (const [moduleId, row] of modules.entries()) {
      if (merged.has(moduleId)) continue;
      if (isChatOnlySkill(moduleId)) continue;
      merged.set(moduleId, {
        moduleId,
        syntheticPath: row.syntheticPath,
        label: row.label,
        isPlaceholder: true,
        status: activeModuleIds.has(moduleId) ? "running" : "idle",
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
