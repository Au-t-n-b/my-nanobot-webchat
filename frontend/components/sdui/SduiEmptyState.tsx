"use client";

import {
  AlertTriangle,
  Circle,
  ClipboardCheck,
  FileText,
  Image as ImageLucide,
  Inbox,
  LayoutDashboard,
  Terminal,
  type LucideIcon,
} from "lucide-react";
import type { SduiTabIconName } from "@/lib/sdui";

type Props = {
  title: string;
  hint?: string;
  icon?: SduiTabIconName;
};

// 与 ``SduiTabs`` 共享的封闭图标集；额外提供 ``inbox`` 作为最常见的"无内容"默认。
const ICON_MAP: Record<SduiTabIconName, LucideIcon> = {
  terminal: Terminal,
  clipboardCheck: ClipboardCheck,
  alertTriangle: AlertTriangle,
  image: ImageLucide,
  fileText: FileText,
  layoutDashboard: LayoutDashboard,
  circle: Circle,
};

/**
 * 空态展示组件：``dashed border + 居中 icon + 标题 + 可选 hint``。
 * 替代仓内"用 Text(color=subtle) 当占位文案"的反模式。
 */
export function SduiEmptyState({ title, hint, icon }: Props) {
  const IconComponent = (icon && ICON_MAP[icon]) || Inbox;
  return (
    <div
      role="status"
      className="flex min-h-[120px] w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-6 text-center"
    >
      <IconComponent size={20} className="ui-text-muted" aria-hidden />
      <p className="text-xs font-medium ui-text-secondary">{title}</p>
      {hint ? <p className="text-[11px] leading-relaxed ui-text-muted">{hint}</p> : null}
    </div>
  );
}
