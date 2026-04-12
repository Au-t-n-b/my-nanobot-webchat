"use client";

import { Fragment, useId } from "react";
import { Check, Loader2, XCircle } from "lucide-react";

import type { SduiStepperDetailItem, SduiStepperStatus, SduiStepperStep } from "@/lib/sdui";

type Props = {
  steps: SduiStepperStep[];
  orientation?: "horizontal" | "vertical";
};

const NODE =
  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors";

function normalizeStatus(status: string | undefined): SduiStepperStatus {
  if (status === "active") return "running";
  if (status === "completed") return "done";
  if (status === "pending") return "waiting";
  if (status === "in_progress") return "running";
  if (status === "failed") return "error";
  if (status === "waiting" || status === "running" || status === "done" || status === "error") return status;
  return "waiting";
}

function detailLineLabel(item: SduiStepperDetailItem): string {
  if (typeof item === "string") return item;
  const normalized = normalizeStatus(item.status);
  const st = normalized === "done" ? "完成" : normalized === "running" ? "进行中" : normalized === "error" ? "异常" : "待处理";
  return `${item.title}（${st}）`;
}

/** 原生 title 用单行友好分隔；悬停层用多行 */
function detailTitleAttr(step: SduiStepperStep): string | undefined {
  if (!step.detail?.length) return undefined;
  return step.detail.map(detailLineLabel).join(" · ");
}

function StepGlyph({ status, stepIndex }: { status: SduiStepperStatus; stepIndex: number }) {
  switch (normalizeStatus(status)) {
    case "waiting":
      return (
        <div
          className={`${NODE} border-2 border-[color-mix(in_oklab,var(--text-muted)_40%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--text-muted)_8%,var(--surface-2))] text-[var(--text-muted)]`}
          aria-label={`步骤 ${stepIndex + 1} 未开始`}
        >
          <span className="text-[11px] font-bold tabular-nums leading-none">{stepIndex + 1}</span>
        </div>
      );
    case "running":
      return (
        <div
          className={`stepper-node-running ${NODE} bg-[color-mix(in_oklab,var(--accent)_16%,var(--surface-2))] ring-2 ring-[color-mix(in_oklab,var(--accent)_50%,var(--border-subtle))]`}
          aria-label={`步骤 ${stepIndex + 1} 进行中`}
        >
          <Loader2 className="h-4 w-4 animate-spin text-[var(--accent)]" />
        </div>
      );
    case "done":
      return (
        <div
          className={`${NODE} bg-[color-mix(in_oklab,var(--success)_22%,transparent)] ring-2 ring-[color-mix(in_oklab,var(--success)_55%,transparent)]`}
          aria-label={`步骤 ${stepIndex + 1} 已完成`}
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
        <div
          className={`${NODE} border-2 border-[var(--border-subtle)] bg-[var(--surface-2)]`}
          aria-hidden
        />
      );
  }
}

function Connector({ prevStatus }: { prevStatus: SduiStepperStatus | undefined }) {
  const normalized = normalizeStatus(prevStatus);
  const segClass =
    normalized === "done"
      ? "bg-[var(--success)]"
      : normalized === "running"
        ? "bg-[color-mix(in_oklab,var(--accent)_55%,var(--border-subtle))]"
        : "bg-[var(--border-subtle)]";
  return (
    <div
      className={["mx-0.5 h-0.5 min-h-[2px] min-w-[8px] flex-1 rounded-full sm:mx-1", segClass].join(" ")}
      style={{ transition: "background-color 320ms ease, opacity 320ms ease" }}
      aria-hidden
    />
  );
}

/** 悬停/聚焦时展示细分步骤；键盘可聚焦 */
function StepDetailPopover({
  step,
  stepIndex,
  children,
  align = "center",
}: {
  step: SduiStepperStep;
  stepIndex: number;
  children: React.ReactNode;
  align?: "center" | "start";
}) {
  const baseId = useId();
  const descId = step.detail?.length ? `${baseId}-desc-${stepIndex}` : undefined;
  const titleTip = detailTitleAttr(step);

  if (!step.detail?.length) {
    return <>{children}</>;
  }

  return (
    <div
      className={[
        "group/step relative flex flex-col",
        align === "center" ? "items-center" : "items-start",
      ].join(" ")}
    >
      <div
        tabIndex={0}
        className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas-rail)]"
        role="group"
        aria-label={step.title}
        aria-describedby={descId}
        title={titleTip}
      >
        {children}
      </div>
      <div
        id={descId}
        role="tooltip"
        className={[
          "pointer-events-none absolute z-20 min-w-[10rem] max-w-[16rem] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-2.5 py-2 text-[10px] leading-snug text-[var(--text-primary)] shadow-[var(--shadow-card)]",
          "opacity-0 transition-opacity duration-150",
          "group-hover/step:opacity-100 group-focus-within/step:opacity-100",
          align === "center" ? "bottom-full left-1/2 mb-1 -translate-x-1/2" : "bottom-full left-0 mb-1",
        ].join(" ")}
      >
        <p className="mb-1 font-semibold text-[var(--text-secondary)]">细分进展</p>
        <ul className="space-y-0.5">
          {step.detail.map((d, i) => (
            <li key={i} className="ui-text-muted">
              {detailLineLabel(d)}
            </li>
          ))}
        </ul>
      </div>
    </div>
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
              <StepDetailPopover step={step} stepIndex={i} align="start">
                <div className="flex flex-col items-center">
                  <StepGlyph status={step.status} stepIndex={i} />
                  {i < steps.length - 1 ? (
                    <div
                      className={[
                        "my-1 min-h-[12px] w-px flex-1 rounded-full",
                        normalizeStatus(step.status) === "done"
                          ? "bg-[var(--success)]"
                          : normalizeStatus(step.status) === "running"
                            ? "bg-[color-mix(in_oklab,var(--accent)_55%,var(--border-subtle))]"
                            : "bg-[var(--border-subtle)]",
                      ].join(" ")}
                      style={{ transition: "background-color 320ms ease, opacity 320ms ease" }}
                    />
                  ) : null}
                </div>
              </StepDetailPopover>
              <div className="min-w-0 flex-1 space-y-1 pb-4">
                <p
                  className={`text-sm font-medium ${
                    normalizeStatus(step.status) === "running"
                      ? "text-[var(--accent)]"
                      : normalizeStatus(step.status) === "done"
                        ? "text-[color-mix(in_oklab,var(--success)_88%,var(--text-primary))]"
                        : "text-[var(--text-muted)]"
                  }`}
                  title={detailTitleAttr(step)}
                >
                  {step.title}
                </p>
                {normalizeStatus(step.status) === "running" ? (
                  <span className="inline-flex w-fit items-center gap-1 rounded-full border border-[color-mix(in_oklab,var(--accent)_35%,transparent)] bg-[color-mix(in_oklab,var(--accent)_10%,var(--surface-2))] px-2 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                    <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden />
                    执行中
                  </span>
                ) : null}
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
            {i > 0 ? <Connector prevStatus={steps[i - 1]?.status} /> : null}
            <div className="flex min-w-0 flex-1 flex-col items-center gap-1 px-0.5" role="listitem">
              <StepDetailPopover step={step} stepIndex={i} align="center">
                <StepGlyph status={step.status} stepIndex={i} />
              </StepDetailPopover>
              <span
                className={`w-full max-w-[9rem] text-center text-[10px] font-medium leading-tight sm:max-w-none sm:text-xs ${
                  normalizeStatus(step.status) === "running"
                    ? "text-[var(--accent)]"
                    : normalizeStatus(step.status) === "done"
                      ? "text-[color-mix(in_oklab,var(--success)_85%,var(--text-secondary))]"
                      : "text-[var(--text-muted)]"
                }`}
                title={detailTitleAttr(step)}
              >
                {step.title}
              </span>
              {normalizeStatus(step.status) === "running" ? (
                <span className="inline-flex max-w-full items-center justify-center gap-0.5 rounded-full border border-[color-mix(in_oklab,var(--accent)_35%,transparent)] bg-[color-mix(in_oklab,var(--accent)_10%,var(--surface-2))] px-1.5 py-px text-[9px] font-medium leading-none text-[var(--accent)]">
                  <Loader2 className="h-2.5 w-2.5 shrink-0 animate-spin" aria-hidden />
                  执行中
                </span>
              ) : null}
            </div>
          </Fragment>
        ))}
      </div>
    </div>
  );
}
