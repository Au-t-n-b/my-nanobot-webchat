"use client";

import type { ReactNode } from "react";

/**
 * 全局系统级面板：设置 / 配置中心 / 资源中心等。
 * 使用遮罩暂时盖住聊天与业务右栏，关闭后回到工作区。
 */
export function SystemShellModal({
  children,
  onClose,
  title,
}: {
  children: ReactNode;
  onClose: () => void;
  /** 可选：屏幕阅读器标题 */
  title?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-6 bg-black/50 backdrop-blur-[1px]"
      role="dialog"
      aria-modal="true"
      aria-label={title ?? "系统设置"}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[92vh] w-full max-w-5xl min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
