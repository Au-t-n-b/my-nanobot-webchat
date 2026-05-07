import type { FileInsightReport } from "@/components/preview/previewTypes";

/** 将 SSE ``report`` 对象收窄为 ``FileInsightReport``；不合法时返回 null */
export function coerceFileInsightReport(raw: Record<string, unknown> | null | undefined): FileInsightReport | null {
  if (!raw || typeof raw !== "object") return null;
  const file_type_guess = String((raw as { file_type_guess?: unknown }).file_type_guess ?? "").trim();
  const summary = String((raw as { summary?: unknown }).summary ?? "").trim();
  const next_action_suggestion = String((raw as { next_action_suggestion?: unknown }).next_action_suggestion ?? "").trim();
  const risk = (raw as { risk_level?: unknown }).risk_level;
  if (risk !== "safe" && risk !== "warning" && risk !== "danger") return null;
  const sn = (raw as { extracted_snippets?: unknown }).extracted_snippets;
  const extracted_snippets = Array.isArray(sn) ? sn.map((x) => String(x)) : [];
  if (!file_type_guess || !summary) return null;
  return {
    file_type_guess,
    summary,
    risk_level: risk,
    extracted_snippets,
    next_action_suggestion: next_action_suggestion || "—",
  };
}
