"use client";

import { useMemo, useState } from "react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { HitlCardShell } from "@/components/sdui/HitlCardShell";

type Props = {
  cardId?: string;
  purpose?: string;
  title?: string;
  label?: string;
  placeholder?: string;
  rows?: number;
  defaultValue?: string;
  submitLabel?: string;
  helpText?: string;
  moduleId?: string;
  nextAction?: string;
  skillName?: string;
  hitlRequestId?: string;
  stateNamespace?: string;
  stepId?: string;
  /** When present, the card is already submitted (read-only). */
  submittedText?: string;
};

export function SduiHitlTextInput(props: Props) {
  const runtime = useSkillUiRuntime();

  const initialSubmitted = (props.submittedText ?? "").trim();
  const [submitted, setSubmitted] = useState(Boolean(initialSubmitted));
  const [text, setText] = useState<string>(initialSubmitted || (props.defaultValue ?? ""));

  const rows = useMemo(() => {
    const r = typeof props.rows === "number" && Number.isFinite(props.rows) ? props.rows : 6;
    return Math.min(30, Math.max(3, r));
  }, [props.rows]);

  const submit = () => {
    if (submitted) return;
    const skill = (props.skillName ?? "").trim();
    const hitlRid = (props.hitlRequestId ?? "").trim();
    const cid = (props.cardId ?? "").trim();
    const pendingRequestId = hitlRid || cid;
    if (!skill || !pendingRequestId) return;

    const namespace = (props.stateNamespace ?? "").trim();
    const sid = (props.stepId ?? "").trim();
    const finalText = text.trim();
    if (!finalText) return;

    setSubmitted(true);
    runtime.lockHitlTextInputCard?.(cid || pendingRequestId, finalText);
    runtime.postToAgent?.(
      JSON.stringify({
        type: "chat_card_intent",
        verb: "skill_runtime_result",
        payload: {
          type: "skill_runtime_result",
          skillName: skill,
          requestId: pendingRequestId,
          status: "ok",
          ...(namespace ? { stateNamespace: namespace } : {}),
          ...(sid ? { stepId: sid } : {}),
          result: { text: finalText },
        },
      }),
    );
  };

  const submitDisabled = submitted || !text.trim();

  return (
    <HitlCardShell eyebrow="需要你填写">
      {props.title ? <p className="text-xs ui-text-secondary leading-relaxed">{props.title}</p> : null}
      {props.helpText ? <p className="ui-text-label ui-text-muted">{props.helpText}</p> : null}
      {props.label ? <div className="text-xs font-semibold ui-text-primary">{props.label}</div> : null}
      <textarea
        className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-0)] px-4 py-3 text-sm ui-text-primary placeholder:ui-text-muted focus:outline-none focus:ring-2 focus:ring-white/10 focus:border-[var(--border-strong)] transition-all resize-y min-h-[4rem]"
        rows={rows}
        placeholder={props.placeholder}
        value={text}
        disabled={submitted}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex items-center justify-end">
        <button
          type="button"
          disabled={submitDisabled}
          onClick={submit}
          className="rounded-lg px-4 py-2 text-xs font-semibold text-white ui-motion-fast transition-opacity disabled:opacity-40"
          style={{ background: "var(--accent)" }}
        >
          {(props.submitLabel ?? "").trim() || "提交"}
        </button>
      </div>
    </HitlCardShell>
  );
}

