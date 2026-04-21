"use client";

import type { ReactNode } from "react";

export type WorkbenchTopNavSlotProps = {
  children: ReactNode;
  /** 顶栏「项目区」容器 class（默认：可收缩、避免挤压右侧控件） */
  className?: string;
};

/**
 * 顶栏项目/工作区增量区插槽，减少 WorkbenchContent 直接堆 JSX。
 */
export function WorkbenchTopNavSlot({ children, className }: WorkbenchTopNavSlotProps) {
  return <div className={className ?? "shrink-0 min-w-0"}>{children}</div>;
}
