"use client";

import { useSyncExternalStore } from "react";

import type { TaskStatusPayload } from "@/hooks/useAgentChat";
import { composeProjectRegistryItems } from "@/lib/projectOverviewRegistry";

export type ProjectModuleRegistryItem = {
  moduleId: string;
  label: string;
  description: string;
  placeholder?: boolean;
  /** 默认 true；为 false 时不进入工作台顶部「流程进度」条（Skill 自行在大盘内展示进度即可） */
  showWorkbenchModuleStepper?: boolean;
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
  showWorkbenchModuleStepper: boolean;
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

export type HydrateProjectOverviewOptions = {
  /**
   * ``merge``（默认）：与现有 taskStatus 做模块/步骤合并，适合与 SSE 交错更新。
   * ``replace``：以 /api/task-status 返回为准（手工改 task_progress.json 存盘后轮询用，避免合并不降 completed）。
   */
  taskStatusMode?: "merge" | "replace";
};

export async function hydrateProjectOverview(
  force = false,
  options?: HydrateProjectOverviewOptions,
): Promise<void> {
  if (!force && hydratePromise) return hydratePromise;
  const taskStatusMode = options?.taskStatusMode ?? "merge";
  hydratePromise = (async () => {
    const [registryItems, taskStatus] = await Promise.all([
      fetchRegistryItems().catch(() => state.registryItems),
      fetchTaskStatusSnapshot().catch(() => state.taskStatus),
    ]);
    setState((prev) => ({
      ...prev,
      registryItems,
      registryLoaded: true,
      taskStatus:
        taskStatus == null
          ? prev.taskStatus
          : taskStatusMode === "replace"
            ? taskStatus
            : mergeTaskStatusSnapshot(prev.taskStatus, taskStatus),
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

/** 将 /api/task-status 中的状态映射为总览用三态 */
function viewStatusFromApi(
  s: TaskStatusPayload["modules"][0]["status"],
): ProjectOverviewModuleView["status"] {
  if (s === "completed") return "completed";
  if (s === "running") return "running";
  return "idle";
}

/** 用 taskId（task_progress 中的 moduleId）在合并后的 module.json 项中查找，用于取 dashboard 等 */
function findRegistryItemForTaskModuleId(
  taskId: string,
  composed: ProjectModuleRegistryItem[],
): ProjectModuleRegistryItem | null {
  const t = String(taskId ?? "").trim();
  for (const r of composed) {
    if (String(r.taskProgress.moduleId).trim() === t) return r;
  }
  for (const r of composed) {
    if (String(r.moduleId).trim() === t) return r;
  }
  return null;
}

/**
 * 主路径：总进度条完全由 ``/api/task-status`` 驱动，而后端自 ``task_progress.json``
 *（及 normalize）生成该 payload。``modules`` 的**顺序、阶段名、子任务**均与磁盘文件一致。
 * module.json 仅作合并项以绑定 `dashboard.dataFile` 等。
 */
function buildOverviewViewsFromTaskStatus(
  taskStatus: TaskStatusPayload,
  registryItems: ProjectModuleRegistryItem[],
): ProjectOverviewModuleView[] {
  const composed = composeProjectRegistryItems(registryItems);
  const rawMain = (taskStatus.modules ?? []).filter((m) => !isHybridTaskModuleId(m.id));
  // 防御性去重：``task_progress.json`` 历史可能落下同 ``moduleId`` 的重复条目（如 jmfz
  // 早期使用 ``moduleId=jmfz``、后改为 ``modeling_simulation_workbench`` 时遗留的脏行），
  // 这里**保留首条**避免后续 ``<li key>`` 重复让 React 报错并错乱阶段大盘的渲染顺序。
  const seenIds = new Set<string>();
  const main: typeof rawMain = [];
  for (const m of rawMain) {
    const id = String(m.id ?? "").trim();
    if (id && seenIds.has(id)) continue;
    if (id) seenIds.add(id);
    main.push(m);
  }
  return main.map((m) => {
    const reg = findRegistryItemForTaskModuleId(m.id, composed);
    const moduleId = (reg?.moduleId ?? m.id).trim() || m.id;
    const steps = Array.isArray(m.steps) ? m.steps : [];
    const doneCount = steps.filter((s) => s.done).length;
    const totalCount = steps.length;
    const progressPct = totalCount ? Math.round((doneCount / totalCount) * 100) : 0;
    return {
      moduleId,
      label: String(m.name || "").trim() || m.id,
      description: reg?.description ?? "",
      syntheticPath: moduleSyntheticPathFromDataFile(
        reg?.dashboard?.dataFile ? String(reg.dashboard.dataFile) : "",
        moduleId,
      ),
      isPlaceholder: !reg || Boolean(reg.placeholder),
      showWorkbenchModuleStepper: reg?.showWorkbenchModuleStepper !== false,
      taskModuleId: m.id,
      taskModuleName: m.name,
      status: viewStatusFromApi(m.status),
      doneCount,
      totalCount,
      progressPct,
      currentStepLabel: steps[doneCount]?.name ?? (totalCount ? "已完成" : "待开始"),
      steps,
    };
  });
}

export function selectProjectOverviewModules(snapshot: ProjectOverviewState): ProjectOverviewModuleView[] {
  const hasFileModules =
    snapshot.taskStatus && Array.isArray(snapshot.taskStatus.modules) && snapshot.taskStatus.modules.length > 0;
  const mainFileModules = hasFileModules
    ? (snapshot.taskStatus?.modules ?? []).filter((m) => !isHybridTaskModuleId(m.id))
    : [];
  const views: ProjectOverviewModuleView[] =
    hasFileModules && mainFileModules.length > 0
      ? buildOverviewViewsFromTaskStatus(snapshot.taskStatus!, snapshot.registryItems)
      : composeProjectRegistryItems(snapshot.registryItems).map((item) => {
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
            showWorkbenchModuleStepper: item.showWorkbenchModuleStepper !== false,
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

  // 不再做前端 Data Sanitizer 加工。``normalize_task_progress_payload`` 已经按
  // ``done==total → completed / done>0 → running / else → pending`` 的单条规则
  // 给出每个 module 的真实状态；状态串行不变量（单 running、前段完整、后段空）
  // 的责任在写入数据源（drivers + ``merge_task_progress_sync_to_disk``）。
  //
  // 历史实现会做「currentIndex 之前强制 completed / 之后强制 idle」的回填，
  // 在 ``task_progress.json`` 包含跨阶段 partial（例如 0/N 的中间段 + 6/6 的
  // 智能分析工作台 + 2/3 的自定义分析）时会把 0 进度的段亮成「已完成」，
  // 与磁盘真相完全相反，因此移除。
  return views;
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
