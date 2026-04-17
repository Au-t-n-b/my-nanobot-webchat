"use client";

import { useState } from "react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { formatLegacyModuleActionBlockedMessage, useLegacyModuleActionAllowed } from "@/lib/legacyModuleGate";

type Props = {
  title: string;
  confirmLabel: string;
  cancelLabel: string;
  cardId?: string;
  /** Matches PendingHitlStore row id (HITL envelope payload.requestId). */
  hitlRequestId?: string;
  moduleId?: string;
  nextAction?: string;
  skillName?: string;
  stateNamespace?: string;
  stepId?: string;
};

export function SduiConfirmCard({
  title,
  confirmLabel,
  cancelLabel,
  cardId,
  hitlRequestId,
  moduleId,
  nextAction,
  skillName,
  stateNamespace,
  stepId,
}: Props) {
  const runtime = useSkillUiRuntime();
  const legacyGate = useLegacyModuleActionAllowed(moduleId);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const postSkillResult = (status: "ok" | "cancel", result: Record<string, unknown>) => {
    const skill = (skillName ?? "").trim();
    const hitlRid = (hitlRequestId ?? "").trim();
    const cid = (cardId ?? "").trim();
    const pendingRequestId = hitlRid || cid;
    const namespace = (stateNamespace ?? "").trim();
    const sid = (stepId ?? "").trim();
    if (!skill || !pendingRequestId) return;
    runtime.postToAgent?.(
      JSON.stringify({
        type: "chat_card_intent",
        verb: "skill_runtime_result",
        payload: {
          type: "skill_runtime_result",
          skillName: skill,
          requestId: pendingRequestId,
          status,
          ...(namespace ? { stateNamespace: namespace } : {}),
          ...(sid ? { stepId: sid } : {}),
          result,
        },
      }),
    );
  };

  const onConfirm = () => {
    setError(null);
    const skill = (skillName ?? "").trim();
    const hitlRid = (hitlRequestId ?? "").trim();
    const cid = (cardId ?? "").trim();
    const pendingRequestId = hitlRid || cid;
    if (skill && pendingRequestId) {
      setDone(true);
      postSkillResult("ok", { confirmed: true });
      return;
    }
    const mid = (moduleId ?? "").trim();
    const na = (nextAction ?? "").trim();
    if (mid && na && cid) {
      if (!legacyGate.allowed) {
        setError(formatLegacyModuleActionBlockedMessage(mid, legacyGate.reason));
        return;
      }
      setDone(true);
      runtime.postToAgent?.(
        JSON.stringify({
          type: "chat_card_intent",
          verb: "module_action",
          cardId: cid,
          payload: {
            moduleId: mid,
            action: na,
            state: { confirmed: true },
          },
        }),
      );
    }
  };

  const onCancel = () => {
    setError(null);
    const skill = (skillName ?? "").trim();
    const hitlRid = (hitlRequestId ?? "").trim();
    const cid = (cardId ?? "").trim();
    const pendingRequestId = hitlRid || cid;
    if (skill && pendingRequestId) {
      setDone(true);
      postSkillResult("cancel", { confirmed: false });
      return;
    }
    const mid = (moduleId ?? "").trim();
    const na = (nextAction ?? "").trim();
    if (mid && na && cid) {
      if (!legacyGate.allowed) {
        setError(formatLegacyModuleActionBlockedMessage(mid, legacyGate.reason));
        return;
      }
      setDone(true);
      runtime.postToAgent?.(
        JSON.stringify({
          type: "chat_card_intent",
          verb: "module_action",
          cardId: cid,
          payload: {
            moduleId: mid,
            action: na,
            state: { confirmed: false },
          },
        }),
      );
    }
  };

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
          需要你的确认
        </span>
        <p className="text-xs ui-text-secondary leading-relaxed">{title}</p>
        {error ? (
          <div
            className="rounded-md px-2.5 py-2 text-[11px] leading-relaxed"
            style={{
              background: "rgba(239,107,115,0.12)",
              border: "1px solid rgba(239,107,115,0.22)",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        ) : null}
      </div>
      <div className="flex gap-2 px-3 py-2.5">
        <button
          type="button"
          disabled={done}
          onClick={onCancel}
          className="flex-1 rounded-md py-2 text-xs font-semibold border transition-opacity disabled:opacity-40"
          style={{ borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          disabled={done}
          onClick={onConfirm}
          className="flex-1 rounded-md py-2 text-xs font-semibold text-white transition-opacity disabled:opacity-40"
          style={{ background: "var(--accent)" }}
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}
