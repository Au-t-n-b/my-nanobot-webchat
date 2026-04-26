"use client";

import { useMemo, useState } from "react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

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
    <div
      className="rounded-lg overflow-hidden border"
      style={{
        background: "color-mix(in oklab, var(--accent) 6%, var(--surface-1))",
        borderColor: "color-mix(in oklab, var(--accent) 22%, transparent)",
        borderLeft: "3px solid var(--accent)",
      }}
    >
      <div
        className="flex flex-col gap-2 px-3 py-2.5 border-b"
        style={{ borderColor: "color-mix(in oklab, var(--accent) 15%, transparent)" }}
      >
        <span className="text-[10px] font-bold tracking-wide uppercase" style={{ color: "var(--accent)" }}>
          需要你填写
        </span>
        {props.title ? <p className="text-xs ui-text-secondary leading-relaxed">{props.title}</p> : null}
        {props.helpText ? <p className="text-[11px] ui-text-muted leading-relaxed">{props.helpText}</p> : null}
      </div>

      <div className="px-3 py-2.5">
        {props.label ? <div className="mb-2 text-xs font-semibold ui-text-primary">{props.label}</div> : null}
        <textarea
          className="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-300 transition-all resize-y min-h-[4rem] dark:border-white/10 dark:bg-zinc-800/50 dark:text-zinc-100 dark:focus:bg-zinc-900 dark:focus:ring-white/10"
          rows={rows}
          placeholder={props.placeholder}
          value={text}
          disabled={submitted}
          onChange={(e) => setText(e.target.value)}
        />

        <div className="mt-3 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={submitDisabled}
            onClick={submit}
            className="rounded-lg px-4 py-2 text-xs font-semibold text-white disabled:opacity-40 transition-opacity"
            style={{ background: "var(--accent)" }}
          >
            {(props.submitLabel ?? "").trim() || "提交"}
          </button>
        </div>
      </div>
    </div>
  );
}

