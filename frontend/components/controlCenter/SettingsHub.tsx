"use client";

import { Settings2, UserRound, Users } from "lucide-react";
import { useEffect } from "react";
import { SettingsPanel } from "@/components/SettingsPanel";
import { AdminMembersPanel } from "@/components/workbench/AdminMembersPanel";
import { ProfilePane } from "@/components/controlCenter/ProfilePane";

export type ControlCenterSettingsPane = "systemSettings" | "profile" | "members";

export function SettingsHub({
  activePane,
  onPaneChange,
  onClose,
  onOpenRemoteUpload,
  showCloseButton = true,
}: {
  activePane: ControlCenterSettingsPane;
  onPaneChange: (pane: ControlCenterSettingsPane) => void;
  onClose: () => void;
  onOpenRemoteUpload?: () => void;
  showCloseButton?: boolean;
}) {
  useEffect(() => {
    // keep for future deep-link side effects
  }, [activePane]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
        <button
          type="button"
          onClick={() => onPaneChange("systemSettings")}
          className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            borderColor: activePane === "systemSettings" ? "var(--accent)" : "var(--border-subtle)",
            background:
              activePane === "systemSettings"
                ? "color-mix(in oklab, var(--accent) 12%, var(--surface-2))"
                : "var(--surface-1)",
            color: activePane === "systemSettings" ? "var(--text-primary)" : "var(--text-secondary)",
          }}
        >
          <Settings2 size={14} aria-hidden />
          系统设置
        </button>
        <button
          type="button"
          onClick={() => onPaneChange("profile")}
          className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            borderColor: activePane === "profile" ? "var(--accent)" : "var(--border-subtle)",
            background: activePane === "profile" ? "color-mix(in oklab, var(--accent) 12%, var(--surface-2))" : "var(--surface-1)",
            color: activePane === "profile" ? "var(--text-primary)" : "var(--text-secondary)",
          }}
        >
          <UserRound size={14} aria-hidden />
          个人中心
        </button>
        <button
          type="button"
          onClick={() => onPaneChange("members")}
          className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            borderColor: activePane === "members" ? "var(--accent)" : "var(--border-subtle)",
            background: activePane === "members" ? "color-mix(in oklab, var(--accent) 12%, var(--surface-2))" : "var(--surface-1)",
            color: activePane === "members" ? "var(--text-primary)" : "var(--text-secondary)",
          }}
        >
          <Users size={14} aria-hidden />
          成员管理
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {activePane === "systemSettings" ? (
          <SettingsPanel onClose={onClose} onOpenRemoteUpload={onOpenRemoteUpload} showCloseButton={showCloseButton} />
        ) : activePane === "profile" ? (
          <div className="min-h-0 flex-1 overflow-auto">
            <ProfilePane onAfterLogout={onClose} />
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-hidden">
            <AdminMembersPanel embedded />
          </div>
        )}
      </div>
    </div>
  );
}

