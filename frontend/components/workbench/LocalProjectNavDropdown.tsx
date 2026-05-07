"use client";

import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { LocalProject } from "@/lib/localProjects";

function ProjectOptionRow({
  project,
  active,
  onSelect,
  onDelete,
}: {
  project: { id: string; name: string };
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="min-w-0 list-none px-1">
      <div
        className={
          "flex min-w-0 items-center gap-1 rounded-lg transition-colors " +
          (active
            ? "bg-[color-mix(in_oklab,var(--accent)_12%,transparent)]"
            : "hover:bg-[var(--surface-2)]")
        }
      >
        <button
          type="button"
          role="option"
          aria-selected={active}
          onClick={onSelect}
          className={
            "min-w-0 flex-1 truncate rounded-lg px-2 py-2 text-left text-sm sm:text-[15px] ui-text-primary " +
            (active ? "font-medium" : "")
          }
        >
          {project.name}
        </button>
        <button
          type="button"
          title="删除该项目"
          aria-label={`删除项目 ${project.name}`}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className={
            "shrink-0 rounded-lg p-2 ui-text-muted ui-motion-fast " +
            "hover:!bg-[color-mix(in_oklab,var(--danger)_12%,transparent)] hover:!text-[var(--danger)]"
          }
        >
          <Trash2 size={16} strokeWidth={2} aria-hidden />
        </button>
      </div>
    </li>
  );
}

function NewProjectAction({ onClick }: { onClick: () => void }) {
  return (
    <div className="border-t border-[var(--border-subtle)]">
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-center gap-1.5 px-2 py-2 text-left text-sm sm:text-[15px] text-[var(--accent)] transition-colors hover:bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]"
      >
        <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-[color-mix(in_srgb,var(--accent)_40%,transparent)] bg-[var(--surface-2)]">
          <Plus className="h-3.5 w-3.5" strokeWidth={2.25} aria-hidden />
        </span>
        新建项目
      </button>
    </div>
  );
}

type Props = {
  projects: LocalProject[];
  selectedId: string;
  onSelect: (id: string) => void;
  onOpenNew: () => void;
  onRequestDelete: (id: string) => void;
  /** 移动端等窄布局：收紧最小宽度 */
  compact?: boolean;
  /** 与流程 Stepper 联动的当前阶段名 */
  currentStageLabel?: string | null;
  /** 模块完成进度 n/N */
  moduleProgressText?: string | null;
};

export function LocalProjectNavDropdown({
  projects,
  selectedId,
  onSelect,
  onOpenNew,
  onRequestDelete,
  compact = false,
  currentStageLabel = null,
  moduleProgressText = null,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const triggerLabel = useMemo(() => {
    if (!selectedId) return projects.length === 0 ? "无项目" : "请选择项目";
    const p = projects.find((x) => x.id === selectedId);
    return p?.name ?? "请选择项目";
  }, [projects, selectedId]);

  const wrapClass = compact
    ? "mr-0 w-full min-w-0 max-w-full shrink"
    : "mr-1.5 w-[min(88vw,18rem)] min-w-[220px] max-w-[20rem] shrink-0 sm:mr-2 max-[480px]:min-w-[min(88vw,220px)]";

  return (
    <div ref={rootRef} className={wrapClass}>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5 sm:gap-x-2.5">
        <span className="hidden shrink-0 whitespace-nowrap text-xs font-bold tracking-wide ui-text-primary sm:inline sm:text-sm">
          项目
        </span>
        <div className="relative min-w-0 flex-1 basis-0 max-w-full">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-haspopup="listbox"
            className={
              "relative flex h-7 w-full min-w-0 items-center rounded-full border border-[color-mix(in_oklab,var(--border-subtle)_72%,var(--text-primary)_16%)] bg-[var(--surface-2)] px-2 py-0.5 text-sm font-medium transition-colors sm:text-[15px] " +
              "ui-text-primary hover:bg-[color-mix(in_oklab,var(--surface-3)_90%,transparent)] " +
              "hover:border-[color-mix(in_oklab,var(--border-subtle)_62%,var(--text-primary)_22%)] " +
              "dark:border-[color-mix(in_oklab,var(--border-subtle)_50%,rgb(255_255_255/0.22))] " +
              "dark:hover:border-[color-mix(in_oklab,var(--border-subtle)_44%,rgb(255_255_255/0.28))]"
            }
          >
            <span className="absolute inset-y-0 left-2 right-7 flex min-w-0 items-center justify-center">
              <span className="w-full min-w-0 truncate text-center">{triggerLabel}</span>
            </span>
            <ChevronDown
              size={14}
              strokeWidth={2}
              className={`absolute right-2 top-1/2 shrink-0 -translate-y-1/2 opacity-70 transition-transform ${open ? "rotate-180" : ""}`}
              aria-hidden
            />
          </button>

          {open ? (
            <div
              className={
                "absolute left-0 right-0 top-[calc(100%+6px)] z-[80] flex w-full min-w-0 flex-col overflow-hidden rounded-xl border border-[color-mix(in_oklab,var(--border-subtle)_72%,var(--text-primary)_14%)] bg-[var(--surface-1)] py-1 shadow-xl " +
                "dark:border-[color-mix(in_oklab,var(--border-subtle)_48%,rgb(255_255_255/0.2))]"
              }
              role="listbox"
            >
              {projects.length === 0 ? (
                <div className="px-3 py-3 text-center text-sm sm:text-[15px] ui-text-muted">暂无项目，请新建</div>
              ) : (
                <ul className="max-h-[min(50dvh,280px)] min-w-0 overflow-y-auto py-0.5 [scrollbar-width:thin]">
                  {projects.map((p) => {
                    const active = p.id === selectedId;
                    return (
                      <ProjectOptionRow
                        key={p.id}
                        project={p}
                        active={active}
                        onSelect={() => {
                          onSelect(p.id);
                          setOpen(false);
                        }}
                        onDelete={() => {
                          onRequestDelete(p.id);
                          setOpen(false);
                        }}
                      />
                    );
                  })}
                </ul>
              )}

              <NewProjectAction
                onClick={() => {
                  setOpen(false);
                  onOpenNew();
                }}
              />
            </div>
          ) : null}
        </div>
        {currentStageLabel ? (
          <>
            <span className="hidden shrink-0 text-[var(--text-muted)] sm:inline" aria-hidden>
              ·
            </span>
            <span
              className="hidden min-w-0 max-w-[12rem] truncate text-xs font-medium ui-text-secondary sm:inline sm:text-sm"
              title={currentStageLabel}
            >
              {currentStageLabel}
            </span>
          </>
        ) : null}
        {moduleProgressText ? (
          <>
            <span className="hidden shrink-0 text-[var(--text-muted)] sm:inline" aria-hidden>
              ·
            </span>
            <span
              className="hidden tabular-nums text-xs text-[var(--text-muted)] sm:inline sm:text-sm"
              title="阶段完成进度"
            >
              {moduleProgressText}
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}
