"use client";

import { Fragment } from "react";
import { Check, Loader2, XCircle } from "lucide-react";

import type { SduiStepperStatus, SduiStepperStep } from "@/lib/sdui";

type Props = {
  steps: SduiStepperStep[];
  orientation?: "horizontal" | "vertical";
};

const NODE = "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors";

function StepGlyph({ status, index }: { status: SduiStepperStatus; index: number }) {
  switch (status) {
    case "waiting":
      return (
        <div
          className={`${NODE} border-2 border-[var(--border-subtle)] bg-[var(--surface-3)] text-[var(--text-muted)]`}
          aria-hidden
        >
          {index}
        </div>
      );
    case "running":
      return (
        <div
          className={`${NODE} bg-blue-500/15 ring-2 ring-blue-500/40 animate-pulse dark:bg-sky-500/15 dark:ring-sky-400/45`}
          aria-hidden
        >
          <Loader2 className="h-4 w-4 animate-spin text-blue-600 dark:text-sky-300" />
        </div>
      );
    case "done":
      return (
        <div
          className={`${NODE} bg-[color-mix(in_oklab,var(--success)_18%,transparent)] ring-2 ring-[color-mix(in_oklab,var(--success)_45%,transparent)]`}
          aria-hidden
        >
          <Check className="h-4 w-4 stroke-[2.5px] text-[var(--success)]" />
        </div>
      );
    case "error":
      return (
        <div className={`${NODE} bg-[color-mix(in_oklab,var(--danger)_15%,transparent)] ring-2 ring-[color-mix(in_oklab,var(--danger)_40%,transparent)]`} aria-hidden>
          <XCircle className="h-4 w-4 text-[var(--danger)]" />
        </div>
      );
    default:
      return (
        <div className={`${NODE} border-2 border-[var(--border-subtle)] bg-[var(--surface-3)] text-[var(--text-muted)]`} aria-hidden>
          {index}
        </div>
      );
  }
}

function Connector({ prevDone }: { prevDone: boolean }) {
  return (
    <div
      className="mx-0.5 h-0.5 min-h-[2px] min-w-[8px] flex-1 rounded-full sm:mx-1"
      style={{
        background: prevDone ? "var(--success)" : "var(--border-subtle)",
      }}
      aria-hidden
    />
  );
}

export function SduiStepper({ steps, orientation = "horizontal" }: Props) {
  if (!steps.length) {
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] px-3 py-4 text-sm text-[var(--text-muted)]">
        Stepper 无步骤
      </div>
    );
  }

  if (orientation === "vertical") {
    return (
      <div
        className="rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] p-3 sm:p-4"
        role="list"
        aria-label="流程步骤"
      >
        <div className="flex flex-col gap-0">
          {steps.map((step, i) => (
            <div key={step.id} className="flex gap-3" role="listitem">
              <div className="flex flex-col items-center">
                <StepGlyph status={step.status} index={i + 1} />
                {i < steps.length - 1 ? (
                  <div
                    className="my-1 min-h-[12px] w-px flex-1 rounded-full"
                    style={{
                      background: step.status === "done" ? "var(--success)" : "var(--border-subtle)",
                    }}
                  />
                ) : null}
              </div>
              <div className="min-w-0 flex-1 pb-4">
                <p
                  className={`text-sm font-medium ${
                    step.status === "running" ? "text-blue-600 dark:text-sky-300" : "text-[var(--text-primary)]"
                  }`}
                >
                  {step.title}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className="w-full min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] px-2 py-4 sm:px-4"
      role="list"
      aria-label="流程步骤"
    >
      <div className="flex w-full min-w-0 items-center">
        {steps.map((step, i) => (
          <Fragment key={step.id}>
            {i > 0 ? <Connector prevDone={steps[i - 1]?.status === "done"} /> : null}
            <div className="flex min-w-0 flex-1 flex-col items-center gap-2 px-0.5" role="listitem">
              <StepGlyph status={step.status} index={i + 1} />
              <span
                className={`w-full max-w-[9rem] text-center text-[10px] font-medium leading-tight sm:max-w-none sm:text-xs ${
                  step.status === "running" ? "text-blue-600 dark:text-sky-300" : "text-[var(--text-secondary)]"
                }`}
              >
                {step.title}
              </span>
            </div>
          </Fragment>
        ))}
      </div>
    </div>
  );
}
