import { getProjectGanttEstimatedDays } from "@/lib/projectGantt/presentation.js";

export type ProjectGanttModule = {
  moduleId: string;
  label: string;
  status: "idle" | "running" | "completed";
  progressLabel?: string;
  steps?: Array<{ id: string; name: string; done: boolean }>;
  isPlaceholder?: boolean;
};

export type ProjectGanttTask = {
  id: string;
  name: string;
  start: string;
  end: string;
  progress: number;
  custom_class: string;
  dependencies?: string;
  moduleId: string;
  status: ProjectGanttModule["status"];
  doneCount: number;
  totalCount: number;
  currentStepLabel: string;
  stepSummary: string;
  estimatedDays: number;
  isPlaceholder: boolean;
};

export type ProjectGanttAnchor = {
  moduleId: string;
  status: ProjectGanttModule["status"];
  start: string;
  end: string;
};

export type ProjectGanttAnchorCache = Map<string, ProjectGanttAnchor>;

type MapOptions = {
  referenceDate?: Date;
  anchorCache?: ProjectGanttAnchorCache;
};

const IDLE_GAP_DAYS = 3;

function clampProgress(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function startOfDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function currentStepLabel(module: ProjectGanttModule, doneCount: number, totalCount: number) {
  if (module.progressLabel?.trim()) return module.progressLabel.trim();
  if (!totalCount) return "待开始";
  if (doneCount >= totalCount) return "已完成";
  return module.steps?.[doneCount]?.name?.trim() || "进行中";
}

function inferDates(
  module: ProjectGanttModule,
  index: number,
  doneCount: number,
  totalCount: number,
  referenceDate: Date,
  previous: ProjectGanttAnchor | undefined,
) {
  if (previous && previous.status === module.status) {
    return { start: previous.start, end: previous.end };
  }

  const duration = getProjectGanttEstimatedDays(totalCount);
  const today = startOfDay(referenceDate);

  if (module.status === "completed") {
    const end = addDays(today, -(index + 1));
    const start = addDays(end, -(duration - 1));
    return { start: formatDate(start), end: formatDate(end) };
  }

  if (module.status === "running") {
    const start = addDays(today, -(Math.max(doneCount, 1) + 1));
    const end = addDays(start, Math.max(duration, 4) - 1);
    return { start: formatDate(start), end: formatDate(end) };
  }

  const start = addDays(today, index * IDLE_GAP_DAYS + 1);
  const end = addDays(start, duration - 1);
  return { start: formatDate(start), end: formatDate(end) };
}

export function mapProjectModulesToGanttTasks(
  modules: ProjectGanttModule[],
  options: MapOptions = {},
): ProjectGanttTask[] {
  const referenceDate = options.referenceDate ?? new Date();
  const cache = options.anchorCache;

  return modules.map((module, index) => {
    const steps = module.steps ?? [];
    const doneCount = steps.filter((step) => step.done).length;
    const totalCount = steps.length;
    const progress =
      module.status === "completed" ? 100 : totalCount ? clampProgress((doneCount / totalCount) * 100) : 0;
    const previous = cache?.get(module.moduleId);
    const dates = inferDates(module, index, doneCount, totalCount, referenceDate, previous);
    const estimatedDays = getProjectGanttEstimatedDays(totalCount);
    const task: ProjectGanttTask = {
      id: module.moduleId,
      moduleId: module.moduleId,
      name: module.label,
      start: dates.start,
      end: dates.end,
      progress,
      status: module.status,
      doneCount,
      totalCount,
      currentStepLabel: currentStepLabel(module, doneCount, totalCount),
      stepSummary: totalCount ? `${doneCount}/${totalCount}` : "0/0",
      estimatedDays,
      isPlaceholder: Boolean(module.isPlaceholder),
      custom_class: `gantt-hue-${index % 8}`,
    };
    cache?.set(module.moduleId, {
      moduleId: module.moduleId,
      status: module.status,
      start: task.start,
      end: task.end,
    });
    return task;
  });
}
