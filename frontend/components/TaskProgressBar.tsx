"use client";

import { Check, CheckCircle2, Circle, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RunStatus } from "@/hooks/useAgentChat";

type ModuleStatus = "pending" | "running" | "completed";
type StepItem = { id: string; name: string; done: boolean };
type ModuleItem = { id: string; name: string; status: ModuleStatus; steps: StepItem[] };
type TaskStatusPayload = {
  updatedAt: string | null;
  overall: { doneCount: number; totalCount: number };
  modules: ModuleItem[];
};

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

export function TaskProgressBar({ runStatus }: { runStatus: RunStatus }) {
  const [data, setData] = useState<TaskStatusPayload | null>(null);
  const [stopped, setStopped] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(aguiRequestPath("/api/task-status"));
      if (!res.ok) return;
      const next = (await res.json()) as TaskStatusPayload;
      setData(next);
      if (next.overall.doneCount >= next.overall.totalCount && next.overall.totalCount > 0) {
        setStopped(true);
      }
    } catch {
      // keep last valid data on fetch errors
    }
  }, []);

  useEffect(() => {
    if (runStatus === "running" || runStatus === "awaitingApproval") {
      setStopped(false);
    }
    if (runStatus === "completed" || runStatus === "error") {
      setStopped(true);
    }
  }, [runStatus]);

  useEffect(() => {
    if (stopped) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    void fetchStatus();
    timerRef.current = setInterval(() => {
      if (!document.hidden) {
        void fetchStatus();
      }
    }, 2000);

    const onVisible = () => {
      if (!document.hidden) {
        void fetchStatus();
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [fetchStatus, stopped]);

  const modules = data?.modules ?? [];
  const overall = useMemo(
    () => ({
      doneCount: data?.overall.doneCount ?? 0,
      totalCount: data?.overall.totalCount ?? 6,
    }),
    [data],
  );

  // Inline compact mode: nodes + connecting lines in a single flex row
  return (
    <div className="flex items-center gap-0 select-none flex-1 min-w-0 px-2">
      {/* Progress pill */}
      <div className="flex items-center gap-1.5 mr-3 shrink-0">
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
        </span>
        <span className="text-[10px] font-semibold tracking-widest text-slate-500 dark:text-slate-400 tabular-nums">
          {overall.doneCount}/{overall.totalCount}
        </span>
      </div>

      {/* Rail: nodes + connectors */}
      <div className="flex items-center flex-1 min-w-0">
        {modules.map((module, index) => (
          <div key={module.id} className="flex items-center flex-1 min-w-0">
            {/* Node with tooltip */}
            <div className="relative group shrink-0" style={{ zIndex: 10 }}>
              {/* Node circle */}
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center transition-all duration-500 cursor-default ${
                  module.status === "completed"
                    ? "bg-emerald-500 text-white shadow-[0_0_10px_rgba(16,185,129,0.5)]"
                    : module.status === "running"
                      ? "bg-blue-600 text-white shadow-[0_0_12px_rgba(37,99,235,0.7)] ring-2 ring-blue-500/40 animate-pulse"
                      : "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400"
                }`}
              >
                {module.status === "completed" && <Check size={11} strokeWidth={3} />}
                {module.status === "running" && <Loader2 size={11} strokeWidth={3} className="animate-spin" />}
                {module.status === "pending" && (
                  <span className="text-[9px] font-bold">{index + 1}</span>
                )}
              </div>

              {/* Tooltip — rendered in a portal-like fixed layer via high z-index */}
              {/* Uses fixed positioning relative to viewport to escape any overflow:hidden parent */}
              <div
                className="absolute opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-150 pointer-events-none"
                style={{
                  top: "calc(100% + 8px)",
                  left: "50%",
                  transform: "translateX(-50%)",
                  zIndex: 9999,
                  width: "200px",
                }}
              >
                {/* Arrow */}
                <div className="flex justify-center mb-[-1px]">
                  <div className="w-2 h-2 rotate-45 border-l border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900" />
                </div>
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.18)] dark:shadow-[0_8px_32px_rgba(0,0,0,0.6)] p-3 text-xs">
                  <div className="font-semibold mb-1.5 pb-1.5 border-b border-slate-100 dark:border-slate-700/50 text-slate-800 dark:text-slate-100">
                    {module.name}
                  </div>
                  {module.steps.length === 0 ? (
                    <p className="text-slate-400 dark:text-slate-500 text-[11px]">暂无细分步骤</p>
                  ) : (
                    <div className="space-y-1.5">
                      {module.steps.map((step) => (
                        <div key={step.id} className="flex items-start justify-between gap-2">
                          <span className={`leading-snug text-[11px] ${step.done ? "text-slate-600 dark:text-slate-300" : "text-slate-400 dark:text-slate-500"}`}>
                            {step.name}
                          </span>
                          <span className="shrink-0 mt-0.5">
                            {step.done
                              ? <CheckCircle2 size={11} className="text-emerald-500" />
                              : <Circle size={11} className="text-slate-300 dark:text-slate-600" />
                            }
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Connector line to next node */}
            {index < modules.length - 1 && (
              <div className="flex-1 h-[3px] mx-0.5 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-700 min-w-0">
                <div
                  className={`h-full transition-all duration-700 ease-in-out rounded-full ${
                    module.status === "completed"
                      ? "w-full bg-emerald-500"
                      : module.status === "running"
                        ? "w-full bg-gradient-to-r from-emerald-500 to-transparent"
                        : "w-0"
                  }`}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
