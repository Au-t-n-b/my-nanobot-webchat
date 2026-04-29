"use client";

import type { ReactNode } from "react";

/**
 * Shared visual shell for chat-side HITL cards (Guide / Confirm / Choice / HitlTextInput).
 *
 * Goals (P1 of SDUI consistency plan):
 * - One container grammar: ``ui-elevation-2`` + accent eyebrow banner.
 * - One typography hierarchy: 10px bold uppercase tracking eyebrow → body within.
 * - One state language: accent for "needs attention", danger for the rare destructive case.
 *
 * NOTE: presentation-only. Does NOT accept any business props (cardId / verb / payload etc.) —
 * those stay on the consuming card and their event flow is untouched.
 */
type Props = {
  /** SHORT uppercase label, e.g. ``引导 · Claw`` / ``需要你的确认``. Always rendered in accent color. */
  eyebrow: string;
  /** Optional pre-eyebrow icon (e.g. ``<Zap size={12} />``). */
  icon?: ReactNode;
  /** ``danger`` swaps eyebrow color to ``--danger``; used for cancel/destructive cards. Default: ``accent``. */
  tone?: "accent" | "danger";
  children: ReactNode;
};

export function HitlCardShell({ eyebrow, icon, tone = "accent", children }: Props) {
  const isDanger = tone === "danger";
  const eyebrowColor = isDanger ? "var(--danger)" : "var(--accent)";
  // ``--accent-soft`` is a baked token; ``--danger`` has no soft variant so we mix on the fly.
  const bannerBg = isDanger
    ? "color-mix(in oklab, var(--danger) 12%, transparent)"
    : "var(--accent-soft)";

  return (
    <div className="ui-elevation-2 rounded-xl overflow-hidden">
      <header
        className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border-subtle)]"
        style={{ background: bannerBg }}
      >
        {icon}
        <span className="ui-text-eyebrow" style={{ color: eyebrowColor }}>
          {eyebrow}
        </span>
      </header>
      <div className="px-4 py-3 space-y-3">{children}</div>
    </div>
  );
}
