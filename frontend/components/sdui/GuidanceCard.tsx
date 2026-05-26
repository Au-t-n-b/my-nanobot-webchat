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

function HintPill({ hint, muted }: { hint: string; muted: boolean }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-[var(--surface-2)] px-2 py-0.5 ui-text-label font-medium ring-1 ring-inset ring-[var(--border-subtle)] ui-text-secondary">
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{
          background: muted ? "var(--text-muted)" : "var(--accent)",
          opacity: muted ? 0.35 : 0.55,
        }}
      />
      {hint}
    </span>
  );
}

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

  const inner = (
    <>
      <div className="flex items-start justify-between gap-3">
        <span
          className={[
            "ui-text-body min-w-0 flex-1 font-semibold",
            disabled ? "ui-text-muted" : "ui-text-primary",
          ].join(" ")}
        >
          {action.label}
        </span>
        {hint ? <HintPill hint={hint} muted={disabled} /> : null}
      </div>
      {description ? (
        <p
          className={[
            "mt-2 ui-text-label whitespace-pre-line",
            "line-clamp-2 group-hover/row:line-clamp-none group-focus-within/row:line-clamp-none",
            disabled ? "ui-text-muted" : "ui-text-secondary",
          ].join(" ")}
        >
          {description}
        </p>
      ) : null}
      {steps.length > 0 ? (
        <ol
          className={[
            "mt-2 ml-4 list-decimal space-y-0.5 ui-text-label ui-text-muted",
            "line-clamp-2 group-hover/row:line-clamp-none group-focus-within/row:line-clamp-none",
          ].join(" ")}
        >
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      ) : null}
    </>
  );

  if (disabled) {
    return (
      <div
        className={[
          "group/row w-full rounded-lg border border-dashed border-[var(--border-subtle)] bg-transparent px-3 py-3 text-left opacity-[0.55]",
          "pointer-events-none select-none",
        ].join(" ")}
        aria-disabled
      >
        {inner}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onTrigger(action)}
      className={[
        "group/row relative w-full rounded-lg border border-transparent bg-[var(--surface-1)] py-3 pl-4 pr-3 text-left ui-motion-fast",
        "ring-1 ring-inset ring-[var(--border-subtle)]",
        "cursor-pointer hover:bg-[var(--interactive-hover-bg)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--interactive-focus-ring)]",
      ].join(" ")}
    >
      <span
        className="pointer-events-none absolute top-2 bottom-2 left-0 w-1 rounded-full bg-[var(--accent)]"
        aria-hidden
      />
      {inner}
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

  const useRows =
    variant === "rows" ||
    (variant !== "buttons" &&
      actions.some(
        (a) =>
          (typeof a.hint === "string" && a.hint.trim().length > 0) ||
          (typeof a.description === "string" && a.description.trim().length > 0) ||
          (Array.isArray(a.steps) && a.steps.length > 0),
      ));

  const contextLines = (context || "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const greeting = contextLines[0] ?? "";
  const bodyLines = greeting ? contextLines.slice(1) : contextLines;

  return (
    <HitlCardShell eyebrow="引导 · Claw" icon={<Zap size={12} style={{ color: "var(--accent)" }} />}>
      {context ? (
        <div className="space-y-2">
          {greeting ? (
            <p className="text-base font-semibold tracking-tight ui-text-primary">{greeting}</p>
          ) : null}
          {bodyLines.map((line, i) => (
            <p key={i} className="ui-text-body ui-text-secondary leading-relaxed whitespace-pre-line">
              {line}
            </p>
          ))}
        </div>
      ) : null}
      {intro ? (
        <p className="mt-2 ui-text-label ui-text-muted leading-relaxed whitespace-pre-line">{intro}</p>
      ) : null}
      {actions.length > 0 && useRows && (
        <ul className="mt-2 flex flex-col gap-2">
          {actions.map((a, i) => (
            <li key={`${a.verb}-${i}`}>
              <ActionRow action={a} cardId={cardId} onTrigger={sendIntent} />
            </li>
          ))}
        </ul>
      )}
      {actions.length > 0 && !useRows && (
        <div className="mt-2 flex flex-wrap gap-2">
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
                a.disabled ? "cursor-not-allowed opacity-60" : "",
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
