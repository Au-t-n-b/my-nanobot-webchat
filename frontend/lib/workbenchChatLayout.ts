/** 工作台会话区 / 分栏 / 预览抽屉布局常量与初始宽度计算（供壳层与拖拽共用） */

import { getLocalStorage, safeSetItem } from "@/lib/browserStorage";

export const RIGHT_PANEL_MAX =
  typeof window !== "undefined" ? Math.floor(window.innerWidth * 0.62) : 900;

export const CHAT_COLUMN_MIN_PX = 320;
/** 导航 + 大盘最小宽 + 分隔条 + 预览条近似总宽；会话列最大 = 视口 − 该预留 */
export const CHAT_COLUMN_LAYOUT_RESERVE_PX = 560;

export function getChatColumnMaxPx(): number {
  if (typeof window === "undefined") return 960;
  return Math.max(CHAT_COLUMN_MIN_PX + 80, window.innerWidth - CHAT_COLUMN_LAYOUT_RESERVE_PX);
}

export const WORKBENCH_CHAT_WIDTH_STORAGE_KEY = "nanobot_workbench_chat_width_v1";
/** 工作台项目总览外层 `p-4` 左右各 1rem */
export const WORKBENCH_OVERVIEW_H_PADDING_PX = 32;
/** 会话区与大盘之间 `w-3` 分隔条 */
export const CHAT_DASHBOARD_SPLITTER_PX = 12;
/** 展开态左侧栏固定宽度（不可拖拽调整） */
export const DEFAULT_NAV_WIDTH_PX = 288;

export function readStoredWorkbenchChatWidthPx(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(WORKBENCH_CHAT_WIDTH_STORAGE_KEY);
    if (raw == null || raw === "") return null;
    const n = Number.parseInt(raw, 10);
    if (!Number.isFinite(n)) return null;
    const cap = getChatColumnMaxPx();
    return Math.max(CHAT_COLUMN_MIN_PX, Math.min(cap, n));
  } catch {
    return null;
  }
}

/** 账号首次进入：中间栏与右侧栏在可视区域内约 1:1（经 min/max 约束） */
export function computeInitialSplitChatWidthPx(navWidthPx: number, viewportInnerWidth: number): number {
  const rowInner = Math.max(0, viewportInnerWidth - WORKBENCH_OVERVIEW_H_PADDING_PX);
  const pairPx = rowInner - navWidthPx - CHAT_DASHBOARD_SPLITTER_PX;
  const half = Math.floor(pairPx / 2);
  const cap = getChatColumnMaxPx();
  return Math.max(CHAT_COLUMN_MIN_PX, Math.min(cap, half));
}

export function getInitialChatWidthState(): number {
  if (typeof window === "undefined") return 240;
  const stored = readStoredWorkbenchChatWidthPx();
  if (stored != null) return stored;
  return computeInitialSplitChatWidthPx(DEFAULT_NAV_WIDTH_PX, window.innerWidth);
}

export function persistWorkbenchChatWidthPx(widthPx: number): void {
  const ls = getLocalStorage();
  if (!ls) return;
  const cap = getChatColumnMaxPx();
  const clamped = Math.max(CHAT_COLUMN_MIN_PX, Math.min(cap, Math.round(widthPx)));
  safeSetItem(ls, WORKBENCH_CHAT_WIDTH_STORAGE_KEY, String(clamped));
}
