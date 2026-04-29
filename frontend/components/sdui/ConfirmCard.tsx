"use client";

import { useState } from "react";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { HitlCardShell } from "@/components/sdui/HitlCardShell";
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
    <HitlCardShell eyebrow="需要你的确认">
      <p className="text-xs ui-text-secondary leading-relaxed">{title}</p>
      {error ? (
        <div
          className="rounded-md px-2.5 py-2 ui-text-label"
          style={{
            background: "color-mix(in oklab, var(--danger) 12%, transparent)",
            border: "1px solid color-mix(in oklab, var(--danger) 22%, transparent)",
            color: "var(--danger)",
          }}
        >
          {error}
        </div>
      ) : null}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={done}
          onClick={onCancel}
          className="flex-1 rounded-md py-2 text-xs font-semibold border ui-motion-fast transition-opacity disabled:opacity-40"
          style={{ borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          disabled={done}
          onClick={onConfirm}
          className="flex-1 rounded-md py-2 text-xs font-semibold text-white ui-motion-fast transition-opacity disabled:opacity-40"
          style={{ background: "var(--accent)" }}
        >
          {confirmLabel}
        </button>
      </div>
    </HitlCardShell>
  );
}
