"use client";

import { useEffect, useMemo, useRef } from "react";
import Gantt from "frappe-gantt";

import { attachGanttChrome } from "@/lib/projectGantt/ganttChrome";
import { attachGanttPanZoom, setGanttZoom } from "@/lib/projectGantt/ganttPanZoom";
import { getFrappeViewMode, projectGanttViewModes, type ProjectGanttViewMode } from "@/lib/projectGantt/frappeViewModes";
import { formatEstimatedDurationLabel, formatPlanningStatusLabel } from "@/lib/projectGantt/presentation.js";
import type { ProjectGanttTask } from "@/lib/projectGantt/taskStatusToFrappeTasks";

type Props = {
  tasks: ProjectGanttTask[];
  viewMode: ProjectGanttViewMode;
  zoom: number;
  scrollToTodaySignal: number;
  onZoomChange: (zoom: number) => void;
  onSelectModule: (moduleId: string) => void;
};

function popupHtml(task: ProjectGanttTask) {
  const planningLabel = formatPlanningStatusLabel(task.isPlaceholder);
  return [
    `<div class="gantt-popup-title">${task.name}</div>`,
    `<div class="gantt-popup-subtitle">${task.currentStepLabel}</div>`,
    `<div class="gantt-popup-details">步骤进度：${task.stepSummary}</div>`,
    planningLabel ? `<div class="gantt-popup-details">阶段标识：${planningLabel}</div>` : "",
    `<div class="gantt-popup-details">预计工期：${formatEstimatedDurationLabel(task.estimatedDays)}</div>`,
    `<div class="gantt-popup-details">模块状态：${task.status === "completed" ? "已完成" : task.status === "running" ? "进行中" : "待开始"}</div>`,
  ]
    .filter(Boolean)
    .join("");
}

export function ProjectGanttCanvas({
  tasks,
  viewMode,
  zoom,
  scrollToTodaySignal,
  onZoomChange,
  onSelectModule,
}: Props) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const ganttRef = useRef<Gantt | null>(null);
  const chromeCleanupRef = useRef<(() => void) | null>(null);
  const panZoomCleanupRef = useRef<(() => void) | null>(null);
  const initialTaskId = useMemo(() => tasks[0]?.id ?? "", [tasks]);

  useEffect(() => {
    const host = hostRef.current;
    const shell = shellRef.current;
    if (!host || !shell || ganttRef.current) return;

    const gantt = new Gantt(host, tasks, {
      view_mode: getFrappeViewMode(viewMode),
      view_modes: projectGanttViewModes(),
      view_mode_select: false,
      today_button: false,
      scroll_to: initialTaskId ? "start" : "today",
      popup_on: "hover",
      popup: ({ task }) => popupHtml(task as ProjectGanttTask),
      readonly: true,
      readonly_dates: true,
      readonly_progress: true,
      container_height: "auto",
      bar_height: 24,
      bar_corner_radius: 10,
      padding: 18,
      lower_header_height: 28,
      upper_header_height: 38,
      lines: "both",
      move_dependencies: false,
      auto_move_label: true,
      infinite_padding: false,
      language: "zh",
    });
    ganttRef.current = gantt;
    setGanttZoom(host, zoom);
    panZoomCleanupRef.current = attachGanttPanZoom({ shell, host, onZoomChange });
    chromeCleanupRef.current = attachGanttChrome({ shell, tasks, onSelectModule });

    return () => {
      chromeCleanupRef.current?.();
      chromeCleanupRef.current = null;
      panZoomCleanupRef.current?.();
      panZoomCleanupRef.current = null;
      host.innerHTML = "";
      ganttRef.current = null;
    };
  }, [initialTaskId, onSelectModule, onZoomChange, tasks, viewMode, zoom]);

  useEffect(() => {
    const gantt = ganttRef.current;
    const shell = shellRef.current;
    const host = hostRef.current;
    if (!gantt || !shell || !host) return;
    gantt.refresh(tasks);
    chromeCleanupRef.current?.();
    chromeCleanupRef.current = attachGanttChrome({ shell, tasks, onSelectModule });
  }, [tasks, onSelectModule]);

  useEffect(() => {
    const gantt = ganttRef.current;
    if (!gantt) return;
    gantt.change_view_mode(getFrappeViewMode(viewMode), true);
  }, [viewMode]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    setGanttZoom(host, zoom);
  }, [zoom]);

  useEffect(() => {
    if (!scrollToTodaySignal) return;
    ganttRef.current?.scroll_current();
  }, [scrollToTodaySignal]);

  return (
    <div ref={shellRef} className="frappe-gantt-shell">
      <div ref={hostRef} className="frappe-gantt-host" />
    </div>
  );
}
