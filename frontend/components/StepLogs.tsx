"use client";

import type { StepLog } from "@/hooks/useAgentChat";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

type Props = { stepLogs: StepLog[] };

export function StepLogs({ stepLogs }: Props) {
  const [open, setOpen] = useState(false);
  if (!stepLogs.length) return null;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 text-xs text-zinc-400 px-1 py-1"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>思考日志（{stepLogs.length}）</span>
      </button>
      {open && (
        <ul className="mt-2 space-y-1 max-h-44 overflow-y-auto text-xs">
          {stepLogs.map((s) => (
            <li key={s.id} className="rounded bg-zinc-900 px-2 py-1 text-zinc-300">
              <span className="text-zinc-500 mr-2">[{s.stepName}]</span>
              {s.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
