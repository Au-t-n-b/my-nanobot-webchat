"use client";

import { FileQuestion, Loader2, Sparkles } from "lucide-react";
import type { BaseRendererProps } from "../previewTypes";

const INSIGHT_MAX_BYTES = 500 * 1024 * 1024;

export type BinaryInsightStatus = "idle" | "requesting" | "ready" | "error";

type Props = BaseRendererProps & {
  name: string;
  insightStatus?: BinaryInsightStatus;
  insightError?: string | null;
  onRequestInsight?: () => void;
};

export function BinaryRenderer(props: Props) {
  if (!props.url) return null;
  const sizeBytes = props.resolution.meta?.sizeBytes;
  const tooLarge = typeof sizeBytes === "number" && sizeBytes > INSIGHT_MAX_BYTES;
  const insightStatus = props.insightStatus ?? "idle";
  const canInsight = Boolean(props.onRequestInsight) && !tooLarge;
  const showInsightUi = Boolean(props.onRequestInsight);

  return (
    <div className="text-sm ui-text-secondary flex flex-col gap-3 items-start">
      <FileQuestion size={32} className="ui-text-muted" />
      <p>无法内联预览此类型，可通过下方链接下载。</p>
      <a href={props.url} download={props.name} className="ui-btn-accent rounded-md px-3 py-1.5">
        打开 / 下载 {props.name}
      </a>

      {showInsightUi ? (
        <div className="w-full max-w-md mt-2 pt-3 border-t border-[var(--border-subtle)] space-y-2">
          <button
            type="button"
            disabled={!canInsight || insightStatus === "requesting"}
            onClick={() => props.onRequestInsight?.()}
            className="group relative w-full overflow-hidden rounded-xl border border-violet-500/35 bg-gradient-to-r from-violet-600/25 via-indigo-600/20 to-cyan-600/20 px-4 py-3 text-left text-sm font-medium text-white shadow-[0_0_24px_rgba(139,92,246,0.18)] transition-all hover:border-violet-400/55 hover:shadow-[0_0_32px_rgba(139,92,246,0.28)] disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
          >
            <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(800px_circle_at_20%_0%,rgba(255,255,255,0.12),transparent_55%)] opacity-70 group-hover:opacity-100" />
            <span className="relative flex items-center gap-2">
              {insightStatus === "requesting" ? (
                <Loader2 className="size-4 shrink-0 animate-spin text-violet-200" aria-hidden />
              ) : (
                <Sparkles className="size-4 shrink-0 text-violet-200" aria-hidden />
              )}
              <span>
                ✨ 让 AI 深度诊断 <span className="text-violet-100/80 font-normal">(Agent Insight)</span>
              </span>
            </span>
          </button>
          {tooLarge ? (
            <p className="text-xs ui-text-muted leading-relaxed">
              文件极其庞大，为确保性能，AI 诊断暂不可用。
            </p>
          ) : null}
          {insightStatus === "error" && props.insightError ? (
            <p className="text-xs" style={{ color: "var(--danger)" }}>
              {props.insightError}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
