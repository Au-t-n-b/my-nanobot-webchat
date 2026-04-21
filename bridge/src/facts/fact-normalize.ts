/** Drop empty streaming chunks so FactFactory does not emit zero-length deltas. */
export function normalizeStreamingText(s: string): string {
  if (!s) return "";
  return s;
}
