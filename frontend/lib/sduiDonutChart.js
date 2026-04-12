/**
 * @typedef {{ label?: string, value?: number, color?: string, action?: unknown }} DonutSegmentLike
 */

/**
 * Normalize donut segments so transient partial patches never crash chart rendering.
 *
 * @param {unknown} segments
 * @returns {DonutSegmentLike[]}
 */
export function normalizeDonutSegments(segments) {
  if (!Array.isArray(segments)) return [];
  return segments.filter((segment) => {
    if (!segment || typeof segment !== "object") return false;
    const value = segment.value;
    return typeof value === "number" && Number.isFinite(value) && value > 0;
  });
}
