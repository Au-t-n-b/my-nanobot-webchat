import type { ProjectGanttTask } from "@/lib/projectGantt/taskStatusToFrappeTasks";
import { formatProjectGanttMetaLabel } from "@/lib/projectGantt/presentation.js";

type ChromeOptions = {
  shell: HTMLElement;
  tasks: ProjectGanttTask[];
  onSelectModule?: (moduleId: string) => void;
};

const BAR_SELECTOR = ".bar-wrapper";

export function attachGanttChrome({ shell, tasks, onSelectModule }: ChromeOptions) {
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const wrappers = shell.querySelectorAll<SVGGElement>(BAR_SELECTOR);
  wrappers.forEach((wrapper) => {
    const task = taskById.get(wrapper.getAttribute("data-id") ?? "");
    if (!task) return;
    wrapper.classList.add(`gantt-state-${task.status}`);
    wrapper.setAttribute("data-gantt-status", task.status);
    wrapper.setAttribute("data-gantt-placeholder", task.isPlaceholder ? "true" : "false");
    wrapper.setAttribute("tabindex", "0");
    wrapper.setAttribute(
      "aria-label",
      `${task.name}，${task.currentStepLabel}，${formatProjectGanttMetaLabel(task)}，${task.stepSummary}，进度 ${task.progress}%`,
    );
  });

  if (!onSelectModule) {
    return () => undefined;
  }

  const openFromTarget = (target: EventTarget | null) => {
    if (!(target instanceof Element)) return;
    const wrapper = target.closest(BAR_SELECTOR);
    if (!(wrapper instanceof SVGGElement)) return;
    const taskId = wrapper.getAttribute("data-id") ?? "";
    const task = taskById.get(taskId);
    if (!task) return;
    onSelectModule(task.moduleId);
  };

  const handleClick = (event: MouseEvent) => {
    openFromTarget(event.target);
  };

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    openFromTarget(event.target);
  };

  shell.addEventListener("click", handleClick);
  shell.addEventListener("keydown", handleKeyDown);
  return () => {
    shell.removeEventListener("click", handleClick);
    shell.removeEventListener("keydown", handleKeyDown);
  };
}
