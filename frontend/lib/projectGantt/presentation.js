/**
 * @param {number | null | undefined} days
 */
export function formatEstimatedDurationLabel(days) {
  const safeDays = Number.isFinite(days) ? Math.max(1, Math.round(days)) : 1;
  return `预计 ${safeDays} 天`;
}

/**
 * @param {boolean | null | undefined} isPlaceholder
 */
export function formatPlanningStatusLabel(isPlaceholder) {
  return isPlaceholder ? "规划中" : "";
}

/**
 * @param {{ estimatedDays?: number | null; isPlaceholder?: boolean | null }} meta
 */
export function formatProjectGanttMetaLabel(meta) {
  return [formatPlanningStatusLabel(meta?.isPlaceholder), formatEstimatedDurationLabel(meta?.estimatedDays)]
    .filter(Boolean)
    .join(" · ");
}

/**
 * 占位阶段和无步骤模块也保留一个稳定工期，避免甘特条长度抖动。
 * @param {number | null | undefined} totalCount
 */
export function getProjectGanttEstimatedDays(totalCount) {
  const safeCount = Number.isFinite(totalCount) ? Math.max(0, Math.round(totalCount)) : 0;
  return Math.max(safeCount, 3);
}
