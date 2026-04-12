"use client";

import { useMemo, useRef, useState } from "react";

import type { ModuleEntry } from "@/components/DashboardNavigator";
import { ProjectGanttCanvas } from "@/components/dashboard/frappe/ProjectGanttCanvas";
import { GanttChartToolbar } from "@/components/dashboard/frappe/GanttChartToolbar";
import { type ProjectGanttAnchorCache, mapProjectModulesToGanttTasks } from "@/lib/projectGantt/taskStatusToFrappeTasks";
import type { ProjectGanttViewMode } from "@/lib/projectGantt/frappeViewModes";

type Props = {
  modules: ModuleEntry[];
  onSelectModule: (moduleId: string) => void;
};

export function ProjectGanttChart({ modules, onSelectModule }: Props) {
  const [viewMode, setViewMode] = useState<ProjectGanttViewMode>("month");
  const [zoom, setZoom] = useState(1);
  const [scrollSignal, setScrollSignal] = useState(0);
  const anchorCacheRef = useRef<ProjectGanttAnchorCache>(new Map());

  const tasks = useMemo(
    () =>
      mapProjectModulesToGanttTasks(
        modules.map((module) => ({
          moduleId: module.moduleId,
          label: module.label,
          status: module.status,
          progressLabel: module.progressLabel,
          steps: module.steps,
          isPlaceholder: module.isPlaceholder,
        })),
        {
          referenceDate: new Date(),
          anchorCache: anchorCacheRef.current,
        },
      ),
    [modules],
  );

  return (
    <div className="space-y-4">
      <GanttChartToolbar
        mode={viewMode}
        zoom={zoom}
        onModeChange={setViewMode}
        onToday={() => setScrollSignal((value) => value + 1)}
        onZoomReset={() => setZoom(1)}
      />
      <ProjectGanttCanvas
        tasks={tasks}
        viewMode={viewMode}
        zoom={zoom}
        scrollToTodaySignal={scrollSignal}
        onZoomChange={setZoom}
        onSelectModule={onSelectModule}
      />
    </div>
  );
}
