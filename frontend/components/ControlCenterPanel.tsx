"use client";

import { Settings2, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { ConfigPanel } from "@/components/ConfigPanel";
import { SettingsHub, type ControlCenterSettingsPane } from "@/components/controlCenter/SettingsHub";

type ControlCenterTab = "config" | "settings";

export function ControlCenterPanel({
  onClose,
  onSaved,
  onOpenRemoteUpload,
  initialTab = "config",
  initialSettingsPane = "systemSettings",
}: {
  onClose: () => void;
  onSaved?: () => void;
  onOpenRemoteUpload?: () => void;
  initialTab?: ControlCenterTab;
  initialSettingsPane?: ControlCenterSettingsPane;
}) {
  const [activeTab, setActiveTab] = useState<ControlCenterTab>(initialTab);
  const [activeSettingsPane, setActiveSettingsPane] = useState<ControlCenterSettingsPane>(initialSettingsPane);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    setActiveSettingsPane(initialSettingsPane);
  }, [initialSettingsPane]);

  return (
    <div className="flex h-[85vh] min-h-[520px] max-h-[92vh] min-w-0 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
        <button
          type="button"
          onClick={() => setActiveTab("config")}
          className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            borderColor: activeTab === "config" ? "var(--accent)" : "var(--border-subtle)",
            background: activeTab === "config" ? "color-mix(in oklab, var(--accent) 12%, var(--surface-2))" : "var(--surface-1)",
            color: activeTab === "config" ? "var(--text-primary)" : "var(--text-secondary)",
          }}
        >
          <Settings2 size={14} />
          配置中心
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("settings")}
          className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            borderColor: activeTab === "settings" ? "var(--accent)" : "var(--border-subtle)",
            background: activeTab === "settings" ? "color-mix(in oklab, var(--accent) 12%, var(--surface-2))" : "var(--surface-1)",
            color: activeTab === "settings" ? "var(--text-primary)" : "var(--text-secondary)",
          }}
        >
          <SlidersHorizontal size={14} />
          远端与基础设置
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "config" ? (
          <ConfigPanel onClose={onClose} onSaved={onSaved} showCloseButton={false} />
        ) : (
          <SettingsHub
            activePane={activeSettingsPane}
            onPaneChange={setActiveSettingsPane}
            onClose={onClose}
            onOpenRemoteUpload={onOpenRemoteUpload}
            showCloseButton={false}
          />
        )}
      </div>
    </div>
  );
}
