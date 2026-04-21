"use client";

import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import type { SduiChoiceOption } from "@/lib/sdui";
import { formatLegacyModuleActionBlockedMessage, useLegacyModuleActionAllowed } from "@/lib/legacyModuleGate";

function optionValue(opt: SduiChoiceOption): string {
  const id = String(opt.id ?? "").trim();
  if (id) return id;
  const v = String(opt.value ?? "").trim();
  if (v) return v;
  return String(opt.label ?? "").trim();
}

const OTHER_VALUE = "__other__";

type Props = {
  title: string;
  options: SduiChoiceOption[];
  cardId?: string;
  /** Matches PendingHitlStore row id (HITL envelope payload.requestId). */
  hitlRequestId?: string;
  moduleId?: string;
  nextAction?: string;
  skillName?: string;
  stateNamespace?: string;
  stepId?: string;
  /** When present, the card is already submitted (read-only). */
  submittedValue?: string;
};

export function SduiChoiceCard({
  title,
  options,
  cardId,
  hitlRequestId,
  moduleId,
  nextAction,
  skillName,
  stateNamespace,
  stepId,
  submittedValue,
}: Props) {
  const runtime = useSkillUiRuntime();
  const initialSubmitted = (submittedValue ?? "").trim();
  const baseValues = options.map(optionValue).filter(Boolean);
  const submittedIsBase = Boolean(initialSubmitted && baseValues.includes(initialSubmitted));
  const initialSelected = initialSubmitted
    ? (submittedIsBase ? initialSubmitted : OTHER_VALUE)
    : null;
  const [selected, setSelected] = useState<string | null>(initialSelected);
  const [otherText, setOtherText] = useState<string>(submittedIsBase ? "" : initialSubmitted);
  const [confirmed, setConfirmed] = useState(Boolean(initialSubmitted));
  const [error, setError] = useState<string | null>(null);
  const legacyGate = useLegacyModuleActionAllowed(moduleId);

  const confirm = () => {
    if (!selected) return;
    setError(null);
    if (confirmed) return;
    const finalValue = selected === OTHER_VALUE ? otherText.trim() : selected;
    if (!finalValue) return;
    const skill = (skillName ?? "").trim();
    const namespace = (stateNamespace ?? "").trim();
    const sid = (stepId ?? "").trim();
    const hitlRid = (hitlRequestId ?? "").trim();
    const pendingRequestId = hitlRid || (cardId ?? "").trim();
    // Skill-first: if the SDUI node is tied to a skill HITL request, always return via skill_runtime_result.
    // (Option 1: platform must not depend on legacy module_action flow.)
    if (skill && pendingRequestId) {
      setConfirmed(true);
      runtime.postToAgent?.(
        JSON.stringify({
          type: "chat_card_intent",
          verb: "skill_runtime_result",
          payload: {
            type: "skill_runtime_result",
            skillName: skill,
            requestId: pendingRequestId,
            status: "ok",
            // action can be omitted; backend will fall back to pending.resume_action
            ...(namespace ? { stateNamespace: namespace } : {}),
            ...(sid ? { stepId: sid } : {}),
            result: { value: finalValue, standard: finalValue },
          },
        }),
      );
      return;
    }

    // Legacy fallback: keep module_action only when no skill context is provided.
    const mid = (moduleId ?? "").trim();
    const na = (nextAction ?? "").trim();
    if (mid && na) {
      if (!legacyGate.allowed) {
        setError(formatLegacyModuleActionBlockedMessage(mid, legacyGate.reason));
        return;
      }
      setConfirmed(true);
      runtime.postToAgent?.(
        JSON.stringify({
          type: "chat_card_intent",
          verb: "module_action",
          cardId,
          payload: {
            moduleId: mid,
            action: na,
            state: { standard: finalValue, value: finalValue },
          },
        }),
      );
      return;
    }

    // Generic present_choices fallback: send plain text back to main chat input.
    if (runtime.onSendText) {
      setConfirmed(true);
      runtime.onSendText(finalValue, { cardId: (cardId ?? "").trim(), submittedValue: finalValue });
      return;
    }
  };

  const finalSelectedValue = selected === OTHER_VALUE ? otherText.trim() : (selected ?? "");
  const confirmDisabled = confirmed || !selected || (selected === OTHER_VALUE && !otherText.trim());

  return (
    <div className="bg-transparent p-0 m-0">
      {/* Single title render (avoid nested wrappers duplicating labels) */}
      <div className="mb-3 text-sm font-semibold ui-text-primary">{title}</div>

      {error ? (
        <div
          className="mb-2 rounded-md px-3 py-2 text-[11px] leading-relaxed"
          style={{
            background: "rgba(239,107,115,0.12)",
            border: "1px solid rgba(239,107,115,0.22)",
            color: "var(--danger)",
          }}
        >
          {error}
        </div>
      ) : null}

      <div className="space-y-2">
        {options.map((opt, idx) => {
          const val = optionValue(opt);
          const isSelected = selected === val;
          return (
            <button
              key={`${cardId ?? "choice"}-${idx}-${val || "opt"}`}
              type="button"
              disabled={confirmed}
              onClick={() => {
                if (confirmed) return;
                setSelected(val);
              }}
              className={[
                "w-full text-left flex items-start gap-3 rounded-md px-3 py-2 text-xs transition-colors duration-200",
                confirmed ? "cursor-default" : "cursor-pointer",
                confirmed ? "" : "hover:bg-white/5",
                isSelected ? "text-[var(--warning)]" : "ui-text-secondary hover:ui-text-primary",
                confirmed ? "cursor-default opacity-90" : "",
              ].join(" ")}
              style={{
                background: "transparent",
                border: isSelected
                  ? "1px solid color-mix(in oklab, var(--warning) 28%, transparent)"
                  : "1px solid transparent",
                boxShadow: isSelected ? "0 0 0 1px rgba(0,0,0,0)" : "none",
              }}
            >
              <span
                className="mt-[2px] w-3.5 h-3.5 rounded-full border flex-shrink-0 flex items-center justify-center"
                style={{
                  borderColor: isSelected
                    ? "color-mix(in oklab, var(--warning) 70%, transparent)"
                    : "color-mix(in oklab, var(--border-subtle) 55%, transparent)",
                  background: isSelected ? "var(--warning)" : "transparent",
                }}
              >
                {isSelected ? <span className="w-1.5 h-1.5 rounded-full bg-black/80" /> : null}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{String(opt.label ?? "")}</span>
                {opt.description ? (
                  <span className="mt-0.5 block text-[11px] ui-text-muted leading-relaxed">
                    {String(opt.description)}
                  </span>
                ) : null}
              </span>
            </button>
          );
        })}

        {/* Other (escape hatch) — inline input when selected */}
        <div
          className={[
            "w-full flex items-start gap-3 rounded-md px-3 py-2 text-xs transition-colors duration-200",
            confirmed ? "cursor-default" : "cursor-pointer hover:bg-white/5",
            selected === OTHER_VALUE ? "text-[var(--warning)]" : "ui-text-secondary",
            confirmed ? "opacity-90" : "",
          ].join(" ")}
          onClick={() => {
            if (confirmed) return;
            setSelected(OTHER_VALUE);
          }}
          role="button"
          tabIndex={confirmed ? -1 : 0}
          onKeyDown={(e) => {
            if (confirmed) return;
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setSelected(OTHER_VALUE);
            }
          }}
          style={{
            border: selected === OTHER_VALUE
              ? "1px solid color-mix(in oklab, var(--warning) 28%, transparent)"
              : "1px solid transparent",
          }}
        >
          <button
            type="button"
            disabled={confirmed}
            onClick={() => {
              if (confirmed) return;
              setSelected(OTHER_VALUE);
            }}
            className="mt-[2px] w-3.5 h-3.5 rounded-full border flex-shrink-0 flex items-center justify-center"
            aria-label="选择其他（自定义意图）"
            onClickCapture={(e) => e.stopPropagation()}
            style={{
              borderColor: selected === OTHER_VALUE
                ? "color-mix(in oklab, var(--warning) 70%, transparent)"
                : "color-mix(in oklab, var(--border-subtle) 55%, transparent)",
              background: selected === OTHER_VALUE ? "var(--warning)" : "transparent",
            }}
          >
            {selected === OTHER_VALUE ? <span className="w-1.5 h-1.5 rounded-full bg-black/80" /> : null}
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex flex-row items-center gap-2 min-w-0">
              <span className="shrink-0 font-medium">其他</span>
              {selected === OTHER_VALUE ? (
                confirmed ? (
                  <span className="min-w-0 truncate ui-text-secondary">{otherText.trim()}</span>
                ) : (
                  <input
                    type="text"
                    value={otherText}
                    onChange={(e) => setOtherText(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onFocus={() => {
                      if (!confirmed) setSelected(OTHER_VALUE);
                    }}
                    placeholder="自定义意图…"
                    className="min-w-0 flex-1 bg-transparent border-b outline-none text-xs"
                    style={{
                      borderColor: otherText.trim()
                        ? "color-mix(in oklab, var(--warning) 55%, transparent)"
                        : "color-mix(in oklab, var(--border-subtle) 60%, transparent)",
                      color: "var(--text-primary)",
                    }}
                    autoFocus
                  />
                )
              ) : (
                <span className="ui-text-muted">（自定义意图）</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={confirmed}
          onClick={() => {
            if (confirmed) return;
            setSelected(null);
            setOtherText("");
            setError(null);
          }}
          className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
        >
          重选
        </button>
        <button
          type="button"
          disabled={confirmDisabled}
          onClick={confirm}
          className="rounded-lg px-4 py-2 text-xs font-semibold text-black disabled:opacity-40 transition-opacity"
          style={{ background: "var(--warning)" }}
          title={confirmDisabled && selected === OTHER_VALUE && !otherText.trim() ? "请输入自定义意图" : undefined}
        >
          确认
        </button>
      </div>
    </div>
  );
}
