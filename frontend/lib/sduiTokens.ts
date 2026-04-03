/**
 * 设计系统间距语义 → 宿主内部像素（仅映射层使用，不出现在 JSON）。
 * 与 docs/sdui-protocol-spec.md 中 SpacingToken 一致。
 */

import type { SpacingToken } from "@/lib/sdui";

export const SPACING_TOKEN_TO_PX: Record<SpacingToken, number> = {
  none: 0,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
};

/** 未指定 gap 时与规范默认档一致 */
const DEFAULT_SPACING: SpacingToken = "md";

export function spacingTokenToGapPx(token: SpacingToken | undefined): number {
  if (token === undefined) return SPACING_TOKEN_TO_PX[DEFAULT_SPACING];
  return SPACING_TOKEN_TO_PX[token] ?? SPACING_TOKEN_TO_PX[DEFAULT_SPACING];
}

/** 将历史数字 gap 映射为最近似的 SpacingToken（兼容旧 JSON） */
export function coerceLegacyGapToToken(g: unknown): SpacingToken | undefined {
  if (g === undefined || g === null) return undefined;
  if (typeof g === "string" && g in SPACING_TOKEN_TO_PX) {
    return g as SpacingToken;
  }
  if (typeof g !== "number" || !Number.isFinite(g)) return undefined;
  if (g <= 0) return "none";
  if (g <= 6) return "xs";
  if (g <= 10) return "sm";
  if (g <= 14) return "md";
  if (g <= 18) return "lg";
  return "xl";
}
