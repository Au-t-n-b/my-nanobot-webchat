"use client";

import { Zap } from "lucide-react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { HitlCardShell } from "@/components/sdui/HitlCardShell";
import type { SduiGuidanceAction } from "@/lib/sdui";

type Props = {
  context: string;
  actions: SduiGuidanceAction[];
  cardId?: string;
  intro?: string;
  variant?: "rows" | "buttons";
};

function ActionRow({
  action,
  cardId,
  onTrigger,
}: {
  action: SduiGuidanceAction;
  cardId?: string;
  onTrigger: (a: SduiGuidanceAction) => void;
}) {
  const disabled = !!action.disabled || !cardId;
  const hint = (action.hint ?? "").trim();
  const description = (action.description ?? "").trim();
  const steps = Array.isArray(action.steps)
    ? action.steps.filter((s) => typeof s === "string" && s.trim())
    : [];

  // Visual variants:
  //   active      → ui-elevation-1 (hairline ring), hover → accent ring 42%
  //   placeholder → ring-1 + text-muted (NOT opacity-60: that compresses contrast & A11y)
  const baseShell = disabled
    ? "bg-[var(--surface-1)] ring-1 ring-inset ring-[var(--border-subtle)] cursor-not-allowed"
    : "ui-elevation-1 hover:ring-1 hover:ring-inset hover:ring-[color-mix(in_oklab,var(--accent)_42%,transparent)] cursor-pointer";

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onTrigger(action)}
      className={[
        "group/row w-full rounded-lg px-3 py-3 text-left ui-motion-fast",
        "transition-[box-shadow,background-color]",
        baseShell,
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <span
          className={[
            "ui-text-body font-semibold truncate",
            disabled ? "ui-text-muted" : "ui-text-primary",
          ].join(" ")}
        >
          {action.label}
        </span>
        {hint ? (
          <kbd
            className={[
              "shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] leading-tight",
              "bg-[color-mix(in_oklab,var(--surface-3)_70%,transparent)]",
              disabled ? "ui-text-muted" : "ui-text-secondary",
            ].join(" ")}
          >
            {hint}
          </kbd>
        ) : null}
      </div>
      {description ? (
        // Default: 1-line clamp; expand fully on hover/focus of this row.
        <p
          className={[
            "mt-2 ui-text-label whitespace-pre-line",
            "line-clamp-1 group-hover/row:line-clamp-none group-focus-within/row:line-clamp-none",
            disabled ? "ui-text-muted" : "ui-text-secondary",
          ].join(" ")}
        >
          {description}
        </p>
      ) : null}
      {steps.length > 0 ? (
        // Default hidden; reveal on hover/focus to keep the card compact.
        <ol className="mt-2 ml-4 hidden list-decimal space-y-0.5 ui-text-label ui-text-muted group-hover/row:block group-focus-within/row:block">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      ) : null}
    </button>
  );
}

export function SduiGuidanceCard({ context, actions, cardId, intro, variant }: Props) {
  const runtime = useSkillUiRuntime();

  const sendIntent = (a: SduiGuidanceAction) => {
    if (!cardId || a.disabled) return;
    runtime.postToAgent?.(
      JSON.stringify({
        type: "chat_card_intent",
        verb: a.verb,
        cardId,
        payload: a.payload !== undefined ? a.payload : null,
      }),
    );
  };

  // Render hint: explicit ``variant === "rows"``, OR any action carries a row-style payload
  // (hint / description / steps).
  const useRows =
    variant === "rows" ||
    (variant !== "buttons" &&
      actions.some(
        (a) =>
          (typeof a.hint === "string" && a.hint.trim().length > 0) ||
          (typeof a.description === "string" && a.description.trim().length > 0) ||
          (Array.isArray(a.steps) && a.steps.length > 0),
      ));

  return (
    <HitlCardShell eyebrow="引导 · Claw" icon={<Zap size={12} style={{ color: "var(--accent)" }} />}>
      {context && (
        <p className="ui-text-body ui-text-secondary whitespace-pre-line">{context}</p>
      )}
      {intro && (
        <p className="ui-text-label ui-text-muted whitespace-pre-line">{intro}</p>
      )}
      {actions.length > 0 && useRows && (
        <ul className="flex flex-col gap-2">
          {actions.map((a, i) => (
            <li key={`${a.verb}-${i}`}>
              <ActionRow action={a} cardId={cardId} onTrigger={sendIntent} />
            </li>
          ))}
        </ul>
      )}
      {actions.length > 0 && !useRows && (
        <div className="flex gap-2 flex-wrap">
          {actions.map((a, i) => (
            <button
              key={`${a.verb}-${i}`}
              type="button"
              disabled={!!a.disabled}
              onClick={() => sendIntent(a)}
              className={[
                "rounded-md px-3 py-1.5 text-xs font-semibold ui-motion-fast",
                i === 0
                  ? "text-white hover:opacity-90"
                  : "border ui-text-muted hover:ui-text-primary hover:bg-[var(--surface-3)]",
                a.disabled ? "opacity-60 cursor-not-allowed" : "",
              ].join(" ")}
              style={i === 0 ? { background: "var(--accent)" } : { borderColor: "var(--border-subtle)" }}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </HitlCardShell>
  );
}
