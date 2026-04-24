"use client";

import { useSyncExternalStore } from "react";

import type { TaskStatusPayload } from "@/hooks/useAgentChat";
import { composeProjectRegistryItems } from "@/lib/projectOverviewRegistry";

export type ProjectModuleRegistryItem = {
  moduleId: string;
  label: string;
  description: string;
  placeholder?: boolean;
  taskProgress: {
    moduleId: string;
    moduleName: string;
    tasks: string[];
  };
  dashboard: {
    docId: string;
    dataFile: string;
  };
};

export type ProjectOverviewModuleView = {
  moduleId: string;
  label: string;
  description: string;
  syntheticPath: string;
  isPlaceholder: boolean;
  taskModuleId: string;
  taskModuleName: string;
  status: "idle" | "running" | "completed";
  doneCount: number;
  totalCount: number;
  progressPct: number;
  currentStepLabel: string;
  steps: Array<{ id: string; name: string; done: boolean }>;
};

type ProjectOverviewState = {
  registryItems: ProjectModuleRegistryItem[];
  registryLoaded: boolean;
  taskStatus: TaskStatusPayload | null;
  activeModuleId: string | null;
  autoGuidedModuleIds: string[];
};

const DEFAULT_SUMMARY = {
  activeCount: 0,
  pendingCount: 0,
  completedCount: 0,
  completionRate: 0,
};

const DEFAULT_OVERALL = {
  doneCount: 0,
  totalCount: 0,
};

const initialState: ProjectOverviewState = {
  registryItems: [],
  registryLoaded: false,
  taskStatus: null,
  activeModuleId: null,
  autoGuidedModuleIds: [],
};

let state: ProjectOverviewState = initialState;
const listeners = new Set<() => void>();
let hydratePromise: Promise<void> | null = null;

function subscribeProjectOverview(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit() {
  for (const listener of listeners) listener();
}

function setState(next: Partial<ProjectOverviewState> | ((prev: ProjectOverviewState) => ProjectOverviewState)) {
  state = typeof next === "function" ? next(state) : { ...state, ...next };
  emit();
}

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

function moduleSyntheticPathFromDataFile(dataFile: string, moduleId: string): string {
  const trimmed = dataFile.trim();
  if (trimmed) return `skill-ui://SduiView?dataFile=${trimmed}`;
  return `skill-ui://SduiView?dataFile=skills/${moduleId}/data/dashboard.json`;
}

function mergeTaskSteps(
  previous: Array<{ id: string; name: string; done: boolean }> | undefined,
  incoming: Array<{ id: string; name: string; done: boolean }> | undefined,
) {
  const merged = new Map<string, { id: string; name: string; done: boolean }>();
  for (const step of previous ?? []) merged.set(step.id, step);
  for (const step of incoming ?? []) {
    const prev = merged.get(step.id);
    merged.set(step.id, {
      id: step.id,
      name: step.name ?? prev?.name ?? step.id,
      done: typeof step.done === "boolean" ? step.done : Boolean(prev?.done),
    });
  }
  return [...merged.values()];
}

/** 混合模式子任务模块：仅用于局部 UI，不得计入项目总览的全局进度。 */
export function isHybridTaskModuleId(moduleId: string): boolean {
  return String(moduleId).startsWith("hybrid:");
}

function modulesForMainProjectProgress(modules: TaskStatusPayload["modules"]): TaskStatusPayload["modules"] {
  return modules.filter((m) => !isHybridTaskModuleId(m.id));
}

function summarizeModules(modules: TaskStatusPayload["modules"]) {
  const main = modulesForMainProjectProgress(modules);
  const completedCount = main.filter((item) => item.status === "completed").length;
  const activeCount = main.filter((item) => item.status === "running").length;
  const pendingCount = Math.max(0, main.length - completedCount - activeCount);
  const totalCount = main.length;
  return {
    activeCount,
    pendingCount,
    completedCount,
    completionRate: totalCount ? Math.round((completedCount / totalCount) * 100) : 0,
  };
}

export function mergeTaskStatusSnapshot(
  previous: TaskStatusPayload | null,
  incoming: TaskStatusPayload,
): TaskStatusPayload {
  if (!previous) {
    const modules = incoming.modules ?? [];
    const summary = summarizeModules(modules);
    const main = modulesForMainProjectProgress(modules);
    return {
      updatedAt: incoming.updatedAt ?? null,
      overall: {
        doneCount: summary.completedCount,
        totalCount: main.length,
      },
      summary,
      modules,
    };
  }

  const previousModules = Array.isArray(previous.modules) ? previous.modules : [];
  const incomingModules = Array.isArray(incoming.modules) ? incoming.modules : [];
  const mergedById = new Map(previousModules.map((moduleState) => [moduleState.id, moduleState]));
  for (const moduleState of incomingModules) {
    const prev = mergedById.get(moduleState.id);
    mergedById.set(moduleState.id, {
      id: moduleState.id,
      name: moduleState.name ?? prev?.name ?? moduleState.id,
      status: moduleState.status ?? prev?.status ?? "pending",
      steps: mergeTaskSteps(prev?.steps, moduleState.steps),
    });
  }

  const modules = [...mergedById.values()];
  const summary = summarizeModules(modules);
  const main = modulesForMainProjectProgress(modules);
  return {
    updatedAt: incoming.updatedAt ?? previous.updatedAt ?? null,
    overall: {
      doneCount: summary.completedCount,
      totalCount: main.length,
    },
    summary,
    modules,
  };
}

async function fetchRegistryItems(): Promise<ProjectModuleRegistryItem[]> {
  const response = await fetch(aguiRequestPath("/api/modules"));
  if (!response.ok) throw new Error(`modules request failed: ${response.status}`);
  const payload = (await response.json()) as { items?: ProjectModuleRegistryItem[] };
  return Array.isArray(payload.items) ? payload.items : [];
}

async function fetchTaskStatusSnapshot(): Promise<TaskStatusPayload | null> {
  const response = await fetch(aguiRequestPath("/api/task-status"));
  if (!response.ok) return null;
  return (await response.json()) as TaskStatusPayload;
}

export async function hydrateProjectOverview(force = false): Promise<void> {
  if (!force && hydratePromise) return hydratePromise;
  hydratePromise = (async () => {
    const [registryItems, taskStatus] = await Promise.all([
      fetchRegistryItems().catch(() => state.registryItems),
      fetchTaskStatusSnapshot().catch(() => state.taskStatus),
    ]);
    setState((prev) => ({
      ...prev,
      registryItems,
      registryLoaded: true,
      taskStatus: taskStatus ? mergeTaskStatusSnapshot(prev.taskStatus, taskStatus) : prev.taskStatus,
    }));
  })();
  try {
    await hydratePromise;
  } finally {
    hydratePromise = null;
  }
}

export function applyTaskStatusSnapshot(payload: TaskStatusPayload) {
  setState((prev) => ({
    ...prev,
    taskStatus: mergeTaskStatusSnapshot(prev.taskStatus, payload),
  }));
}

export function selectProjectModule(moduleId: string | null) {
  setState((prev) => ({
    ...prev,
    activeModuleId: moduleId?.trim() || null,
  }));
}

export function markProjectModuleAutoGuided(moduleId: string) {
  const trimmed = moduleId.trim();
  if (!trimmed) return;
  setState((prev) => {
    if (prev.autoGuidedModuleIds.includes(trimmed)) return prev;
    return {
      ...prev,
      autoGuidedModuleIds: [...prev.autoGuidedModuleIds, trimmed],
    };
  });
}

export function resetProjectOverviewSessionState() {
  setState((prev) => ({
    ...prev,
    activeModuleId: null,
    autoGuidedModuleIds: [],
  }));
}

function matchTaskModule(
  taskStatus: TaskStatusPayload | null,
  registryItem: ProjectModuleRegistryItem,
) {
  const modules = taskStatus?.modules ?? [];
  return (
    modules.find((item) => item.id === registryItem.taskProgress.moduleId) ??
    modules.find((item) => item.name === registryItem.taskProgress.moduleName) ??
    modules.find((item) => item.id === registryItem.moduleId) ??
    null
  );
}

export function selectProjectOverviewModules(snapshot: ProjectOverviewState): ProjectOverviewModuleView[] {
  const views: ProjectOverviewModuleView[] = composeProjectRegistryItems(snapshot.registryItems).map((item) => {
    const taskModule = matchTaskModule(snapshot.taskStatus, item);
    const steps = taskModule?.steps ?? [];
    const doneCount = steps.filter((step) => step.done).length;
    const totalCount = steps.length;
    const progressPct = totalCount ? Math.round((doneCount / totalCount) * 100) : 0;
    const st: ProjectOverviewModuleView["status"] =
      taskModule?.status === "completed"
        ? "completed"
        : taskModule?.status === "running"
          ? "running"
          : "idle";
    return {
      moduleId: item.moduleId,
      label: item.label,
      description: item.description,
      syntheticPath: moduleSyntheticPathFromDataFile(item.dashboard.dataFile, item.moduleId),
      isPlaceholder: Boolean(item.placeholder),
      taskModuleId: item.taskProgress.moduleId,
      taskModuleName: item.taskProgress.moduleName,
      status: st,
      doneCount,
      totalCount,
      progressPct,
      currentStepLabel: steps[doneCount]?.name ?? (totalCount ? "已完成" : "待开始"),
      steps,
    };
  });

  // --- Data Sanitizer: 强制串行状态推导（避免 1&3 同时 running 的脏流） ---
  // currentIndex：索引最靠后的、且 (status=running 或已有进度) 的模块
  // - 已有进度：doneCount>0 或 progressPct>0
  const currentIndex = (() => {
    for (let i = views.length - 1; i >= 0; i -= 1) {
      const m = views[i]!;
      const hasProgress = (m.doneCount ?? 0) > 0 || (m.progressPct ?? 0) > 0;
      if (m.status === "running" || hasProgress) return i;
    }
    return -1;
  })();

  if (currentIndex < 0) {
    return views.map((m) => (m.status === "idle" ? m : { ...m, status: "idle" as const }));
  }

  return views.map((m, i) => {
    if (i < currentIndex) return m.status === "completed" ? m : { ...m, status: "completed" as const };
    if (i === currentIndex) return m.status === "running" ? m : { ...m, status: "running" as const };
    return m.status === "idle" ? m : { ...m, status: "idle" as const };
  });
}

export function getProjectOverviewState() {
  return state;
}

export function getInitialProjectOverviewState() {
  return initialState;
}

export function useProjectOverviewStore<T>(selector: (snapshot: ProjectOverviewState) => T): T {
  const snapshot = useSyncExternalStore(
    subscribeProjectOverview,
    getProjectOverviewState,
    getInitialProjectOverviewState,
  );
  return selector(snapshot);
}

export function selectProjectOverviewSummary(snapshot: ProjectOverviewState) {
  return snapshot.taskStatus?.summary ?? DEFAULT_SUMMARY;
}

export function selectProjectOverviewOverall(snapshot: ProjectOverviewState) {
  return snapshot.taskStatus?.overall ?? DEFAULT_OVERALL;
}

export function selectProjectTaskStatus(snapshot: ProjectOverviewState) {
  return snapshot.taskStatus;
}
