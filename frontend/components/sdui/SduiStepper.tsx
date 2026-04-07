"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

import type { SduiStepperStatus, SduiStepperStep } from "@/lib/sdui";

type Props = {
  steps: SduiStepperStep[];
  orientation?: "horizontal" | "vertical";
};

function StepGlyph({ status }: { status: SduiStepperStatus }) {
  const base = "h-5 w-5 shrink-0 sm:h-6 sm:w-6";
  switch (status) {
    case "waiting":
      return <Circle className={base} style={{ color: "var(--text-muted)" }} strokeWidth={2} aria-hidden />;
    case "running":
      return (
        <Loader2
          className={`${base} animate-spin`}
          style={{ color: "var(--warning)" }}
          aria-hidden
        />
      );
    case "done":
      return <CheckCircle2 className={base} style={{ color: "var(--success)" }} aria-hidden />;
    case "error":
      return <XCircle className={base} style={{ color: "var(--danger)" }} aria-hidden />;
    default:
      return <Circle className={base} style={{ color: "var(--text-muted)" }} aria-hidden />;
  }
}

export function SduiStepper({ steps, orientation = "horizontal" }: Props) {
  if (!steps.length) {
    return (
      <div
        className="rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] px-3 py-4 text-sm text-[var(--text-muted)]"
      >
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
                <StepGlyph status={step.status} />
                {i < steps.length - 1 ? (
                  <div
                    className="my-1 min-h-[12px] w-px flex-1 rounded-full"
                    style={{
                      background:
                        step.status === "done" ? "var(--success)" : "var(--border-subtle)",
                    }}
                  />
                ) : null}
              </div>
              <div className="min-w-0 flex-1 pb-4">
                <p
                  className={`text-sm font-medium ${
                    step.status === "running" ? "text-[var(--accent)]" : "text-[var(--text-primary)]"
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
      className="w-full min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] px-2 py-3 sm:px-4 sm:py-4"
      role="list"
      aria-label="流程步骤"
    >
      <div className="flex w-full min-w-0 items-center">
        {steps.map((step, i) => (
          <div key={step.id} className="flex min-w-0 flex-1 items-center" role="listitem">
            {i > 0 ? (
              <div
                className="mx-1 h-0.5 min-w-[8px] flex-1 rounded-full sm:mx-2"
                style={{
                  background:
                    steps[i - 1]?.status === "done" ? "var(--success)" : "var(--border-subtle)",
                }}
                aria-hidden
              />
            ) : null}
            <div className="flex min-w-0 max-w-[26%] flex-col items-center gap-1.5 sm:max-w-[22%]">
              <StepGlyph status={step.status} />
              <span
                className={`w-full text-center text-[10px] font-medium leading-tight sm:text-xs ${
                  step.status === "running"
                    ? "text-[var(--accent)]"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                {step.title}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
