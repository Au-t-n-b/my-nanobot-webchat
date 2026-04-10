"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SkillUiBootstrapEvent, SkillUiDataPatchEvent } from "@/hooks/useAgentChat";
import { ProjectOverview } from "@/components/dashboard/ProjectOverview";
import { ModuleDashboard } from "@/components/dashboard/ModuleDashboard";

export type ModuleEntry = {
  moduleId: string;
  syntheticPath: string;
  label: string;
  status: "running" | "done" | "idle";
  lastPatchMs: number;
};

type Props = {
  skillUiPatchEvent: SkillUiDataPatchEvent | null | undefined;
  skillUiBootstrapEvent: SkillUiBootstrapEvent | null | undefined;
  onOpenPreview: (path: string) => void;
  postToAgent: (text: string) => void;
  isAgentRunning: boolean;
  activeSkillName?: string | null;
};

function extractModuleId(syntheticPath: string): string | null {
  const m = syntheticPath.match(/\/skills\/([^/]+)\//);
  return m ? m[1] : null;
}

function moduleLabel(id: string): string {
  return id.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DashboardNavigator({
  skillUiPatchEvent,
  skillUiBootstrapEvent,
  onOpenPreview,
  postToAgent,
  isAgentRunning,
  activeSkillName,
}: Props) {
  const [view, setView] = useState<"overview" | "module">("overview");
  const [activeModuleId, setActiveModuleId] = useState<string | null>(null);
  const [modules, setModules] = useState<Map<string, ModuleEntry>>(new Map());
  const [visible, setVisible] = useState(true);
  const userOverrideRef = useRef(false);

  useEffect(() => {
    const syntheticPath = skillUiPatchEvent?.syntheticPath ?? skillUiBootstrapEvent?.syntheticPath;
    if (!syntheticPath) return;
    const moduleId = extractModuleId(syntheticPath);
    if (!moduleId) return;

    const now = Date.now();
    setModules((prev) => {
      const next = new Map(prev);
      const existing = next.get(moduleId);
      next.set(moduleId, {
        moduleId,
        syntheticPath,
        label: existing?.label ?? moduleLabel(moduleId),
        status: "running",
        lastPatchMs: now,
      });
      return next;
    });

    if (!userOverrideRef.current) {
      if (activeModuleId !== moduleId || view !== "module") {
        switchToModule(moduleId, false);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillUiPatchEvent, skillUiBootstrapEvent]);

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setModules((prev) => {
        let changed = false;
        const next = new Map(prev);
        for (const [id, entry] of next) {
          if (entry.status === "running" && now - entry.lastPatchMs > 10_000) {
            next.set(id, { ...entry, status: "done" });
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const fadeSwitch = useCallback((fn: () => void) => {
    setVisible(false);
    setTimeout(() => {
      fn();
      setVisible(true);
    }, 300);
  }, []);

  const switchToModule = useCallback((moduleId: string, byUser: boolean) => {
    if (byUser) userOverrideRef.current = true;
    fadeSwitch(() => {
      setActiveModuleId(moduleId);
      setView("module");
    });
  }, [fadeSwitch]);

  const switchToOverview = useCallback(() => {
    userOverrideRef.current = false;
    fadeSwitch(() => setView("overview"));
  }, [fadeSwitch]);

  const activeEntry = activeModuleId ? modules.get(activeModuleId) ?? null : null;

  return (
    <div
      className="h-full min-h-0 flex flex-col transition-opacity duration-300"
      style={{ opacity: visible ? 1 : 0 }}
    >
      {view === "overview" ? (
        <ProjectOverview
          modules={[...modules.values()]}
          onSelectModule={(id) => switchToModule(id, true)}
        />
      ) : (
        <ModuleDashboard
          entry={activeEntry}
          allModules={[...modules.values()]}
          onSelectModule={(id) => switchToModule(id, true)}
          onBack={switchToOverview}
          skillUiPatchEvent={skillUiPatchEvent}
          skillUiBootstrapEvent={skillUiBootstrapEvent}
          onOpenPreview={onOpenPreview}
          postToAgent={postToAgent}
          isAgentRunning={isAgentRunning}
          activeSkillName={activeSkillName}
        />
      )}
    </div>
  );
}
