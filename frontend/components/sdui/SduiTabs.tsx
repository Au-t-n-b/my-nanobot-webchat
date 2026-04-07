"use client";

import { useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  Circle,
  ClipboardCheck,
  FileText,
  Image as ImageLucide,
  LayoutDashboard,
  Terminal,
} from "lucide-react";

import type { SduiTabIconName, SduiTabPanel } from "@/lib/sdui";
import { SduiNodeView } from "@/components/sdui/SduiNodeView";
import { stableChildKey } from "@/lib/sduiKeys";

const TAB_ICON_MAP: Record<SduiTabIconName, LucideIcon> = {
  terminal: Terminal,
  clipboardCheck: ClipboardCheck,
  alertTriangle: AlertTriangle,
  image: ImageLucide,
  fileText: FileText,
  layoutDashboard: LayoutDashboard,
  circle: Circle,
};

type Props = {
  tabs: SduiTabPanel[];
  defaultTabId?: string;
  pathPrefix: string;
};

export function SduiTabs({ tabs, defaultTabId, pathPrefix }: Props) {
  const safeTabs = tabs.length > 0 ? tabs : [];

  const initialId = useMemo(() => {
    if (defaultTabId && safeTabs.some((t) => t.id === defaultTabId)) {
      return defaultTabId;
    }
    return safeTabs[0]?.id ?? "";
  }, [defaultTabId, safeTabs]);

  const [activeId, setActiveId] = useState(initialId);

  const activePanel = useMemo(
    () => safeTabs.find((t) => t.id === activeId) ?? safeTabs[0],
    [safeTabs, activeId],
  );

  if (safeTabs.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] px-3 py-4 text-sm text-[var(--text-muted)]">
        Tabs 无可用标签页
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--paper-card)] shadow-sm">
      <div
        className="flex min-h-0 w-full flex-shrink-0 flex-wrap gap-0 border-b border-[var(--border-subtle)] bg-[var(--canvas-rail)] px-1"
        role="tablist"
      >
        {safeTabs.map((tab) => {
          const isActive = tab.id === activeId;
          const Icon = tab.icon ? TAB_ICON_MAP[tab.icon] : null;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={[
                "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-xs font-medium transition-colors sm:text-sm",
                isActive
                  ? "border-[var(--accent)] text-[var(--text-primary)]"
                  : "border-transparent text-[var(--text-muted)] hover:bg-[var(--surface-3)]/50 hover:text-[var(--text-secondary)]",
              ].join(" ")}
              onClick={() => setActiveId(tab.id)}
            >
              {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 opacity-90 sm:h-4 sm:w-4" aria-hidden /> : null}
              <span className="truncate">{tab.label}</span>
            </button>
          );
        })}
      </div>
      <div
        className="min-h-0 min-w-0 flex-1 overflow-auto bg-[var(--surface-1)] p-3 sm:p-4"
        role="tabpanel"
      >
        {activePanel?.children?.map((child, i) => {
          const seg = stableChildKey(child, i, `${pathPrefix}/tab:${activePanel.id}`);
          return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;
        })}
      </div>
    </div>
  );
}
