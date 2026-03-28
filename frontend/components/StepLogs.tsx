"use client";

import type { ReactNode } from "react";
import type { RunStatus, StepLog } from "@/hooks/useAgentChat";
import { CheckCircle2, ChevronDown, ChevronRight, CircleDashed, ShieldAlert, TriangleAlert } from "lucide-react";
import { useState } from "react";

type Props = { stepLogs: StepLog[]; runStatus: RunStatus; statusMessage: string; runModel?: string | null };

function statusMeta(runStatus: RunStatus): { label: string; className: string; icon: ReactNode } {
  switch (runStatus) {
    case "running":
      return { label: "执行中", className: "ui-status-running", icon: <CircleDashed size={13} className="animate-spin" /> };
    case "awaitingApproval":
      return { label: "等待确认", className: "ui-status-warning", icon: <ShieldAlert size={13} /> };
    case "completed":
      return { label: "已完成", className: "ui-status-success", icon: <CheckCircle2 size={13} /> };
    case "error":
      return { label: "失败", className: "ui-status-danger", icon: <TriangleAlert size={13} /> };
    default:
      return { label: "待命", className: "ui-text-muted", icon: <CircleDashed size={13} /> };
  }
}

export function StepLogs({ stepLogs, runStatus, statusMessage, runModel }: Props) {
  const [open, setOpen] = useState(false);
  const meta = statusMeta(runStatus);
  if (!stepLogs.length && runStatus === "idle") return null;

  return (
    <div className="ui-card rounded-xl p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={meta.className}>{meta.icon}</span>
          <div>
            <p className={`text-xs font-medium ${meta.className}`}>{meta.label}</p>
            <p className="text-xs ui-text-secondary">{statusMessage}</p>
            {runModel ? <p className="text-[11px] ui-text-muted mt-0.5">模型：{runModel}</p> : null}
          </div>
        </div>
        {stepLogs.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="ui-btn-ghost inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs"
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            详情
          </button>
        )}
      </div>

      {open && (
        <ul className="mt-3 space-y-1.5 max-h-44 overflow-y-auto text-xs">
          {stepLogs.map((s) => (
            <li key={s.id} className="ui-subtle rounded-lg px-2.5 py-2 ui-text-secondary">
              <span className="ui-text-muted mr-2">[{s.stepName === "tool" ? "工具" : "分析"}]</span>
              {s.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
