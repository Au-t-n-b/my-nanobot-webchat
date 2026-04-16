"use client";

import { ChevronLeft } from "lucide-react";
import type { ModuleEntry } from "@/components/DashboardNavigator";
import type { SkillUiDataPatchEvent } from "@/hooks/useAgentChat";
import { SkillUiWrapper } from "@/components/SkillUiWrapper";

type Props = {
  entry: ModuleEntry | null;
  allModules: ModuleEntry[];
  onSelectModule: (id: string) => void;
  onBack: () => void;
  skillUiPatchEvent: SkillUiDataPatchEvent | null | undefined;
  onOpenPreview: (path: string) => void;
  postToAgent: (text: string) => void;
  isAgentRunning: boolean;
  activeSkillName?: string | null;
};

export function ModuleDashboard({
  entry,
  allModules,
  onSelectModule,
  onBack,
  skillUiPatchEvent,
  onOpenPreview,
  postToAgent,
  isAgentRunning,
}: Props) {
  return (
    <div className="h-full min-h-0 flex flex-col">
      <div
        className="flex items-stretch shrink-0 border-b border-[var(--border-subtle)] overflow-x-auto"
        style={{ background: "var(--surface-1)" }}
      >
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1 px-3 py-2 text-xs ui-text-muted hover:ui-text-primary border-r border-[var(--border-subtle)] shrink-0 transition-colors"
        >
          <ChevronLeft size={13} />
          总览
        </button>

        {allModules.map((m) => {
          const isActive = m.moduleId === entry?.moduleId;
          return (
            <button
              key={m.moduleId}
              type="button"
              onClick={() => onSelectModule(m.moduleId)}
              className={[
                "flex items-center gap-1.5 px-4 py-2 text-xs font-medium border-r border-[var(--border-subtle)] shrink-0 transition-colors relative",
                isActive
                  ? "text-[var(--accent)] after:absolute after:bottom-0 after:inset-x-0 after:h-0.5 after:bg-[var(--accent)] after:rounded-t"
                  : "ui-text-muted hover:ui-text-primary",
              ].join(" ")}
            >
              {m.status === "running" && (
                <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse shadow-[0_0_5px_var(--accent)]" />
              )}
              {m.label}
            </button>
          );
        })}

        {/* Skill-First (Option 1): entry/reset actions must be defined in the skill dashboard (SDUI). */}
      </div>

      <div className="dashboard-density-viewport flex-1 min-h-0 overflow-hidden">
        {entry ? (
          <SkillUiWrapper
            key={entry.syntheticPath}
            syntheticPath={entry.syntheticPath}
            incomingPatchEvent={
              skillUiPatchEvent?.syntheticPath === entry.syntheticPath
                ? skillUiPatchEvent
                : null
            }
            onOpenPreview={onOpenPreview}
            postToAgent={postToAgent}
            isAgentRunning={isAgentRunning}
          />
        ) : (
          <div className="flex items-center justify-center h-full ui-text-muted text-sm">
            选择一个模块查看大盘
          </div>
        )}
      </div>
    </div>
  );
}
