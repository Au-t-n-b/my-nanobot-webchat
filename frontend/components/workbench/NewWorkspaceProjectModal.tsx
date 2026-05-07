"use client";

import { ChevronDown, FolderPlus, X } from "lucide-react";
import type { ChangeEvent, ReactNode } from "react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  DELIVERY_FEATURE_OPTIONS,
  GROUP_SELECT_OPTIONS,
  SCALE_SELECT_OPTIONS,
  SCENARIO_SELECT_OPTIONS,
  type WorkspaceProjectCreatePayload,
  type WorkspaceProjectFormMeta,
  emptyWorkspaceProjectFormMeta,
} from "@/lib/workspaceProjectCreate";

type Props = {
  open: boolean;
  onDismiss: () => void;
  onCreate: (payload: WorkspaceProjectCreatePayload) => Promise<void>;
};

const inputClass =
  "w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2.5 text-sm sm:text-[15px] ui-text-primary " +
  "focus:outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--accent)_45%,transparent)] " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const dateInputClass = inputClass + " dark:[color-scheme:dark]";

function NativeSelectWithChevron({
  id,
  value,
  disabled,
  onChange,
  children,
}: {
  id: string;
  value: string;
  disabled?: boolean;
  onChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  children: ReactNode;
}) {
  return (
    <div className="relative w-full">
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={onChange}
        className={`${inputClass} peer w-full cursor-pointer appearance-none pr-11`}
      >
        {children}
      </select>
      <ChevronDown
        size={18}
        strokeWidth={2}
        className="pointer-events-none absolute right-3 top-1/2 z-[1] -translate-y-1/2 ui-text-muted ui-motion-fast peer-hover:text-[var(--text-secondary)] peer-focus-visible:!text-[var(--accent)] peer-disabled:opacity-40"
        aria-hidden
      />
    </div>
  );
}

const CHIP_OPTION_BASE =
  "inline-flex min-h-[2.25rem] min-w-[4.5rem] shrink-0 items-center justify-center rounded-full border px-3 py-2 text-sm font-medium " +
  "transition-[color,background-color,border-color,box-shadow,transform] duration-150 sm:text-[15px] " +
  "active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 ";

const chipInactive =
  "border-[var(--border-subtle)] bg-[var(--surface-2)] ui-text-secondary hover:border-[color-mix(in_oklab,var(--border-subtle)_120%,transparent)] hover:bg-[var(--surface-3)] hover:ui-text-primary";

const labelClass =
  "mb-1.5 block text-sm font-semibold leading-snug ui-text-primary sm:text-[15px]";

export function NewWorkspaceProjectModal({ open, onDismiss, onCreate }: Props) {
  const titleId = useId();
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [meta, setMeta] = useState<WorkspaceProjectFormMeta>(emptyWorkspaceProjectFormMeta);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName("");
    setMeta(emptyWorkspaceProjectFormMeta());
    setError(null);
    setBusy(false);
    const t = window.setTimeout(() => nameRef.current?.focus(), 50);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onDismiss]);

  const toggleDelivery = useCallback((opt: string) => {
    setMeta((m) => ({
      ...m,
      deliveryFeatures: m.deliveryFeatures.includes(opt)
        ? m.deliveryFeatures.filter((x) => x !== opt)
        : [...m.deliveryFeatures, opt],
    }));
    setError(null);
  }, []);

  const submit = useCallback(async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("请输入项目名称");
      nameRef.current?.focus();
      return;
    }
    const code = meta.projectCode.trim();
    if (!code) {
      setError("请输入项目编码");
      document.getElementById("ws-project-code")?.focus();
      return;
    }
    if (!meta.scenario.trim()) {
      setError("请选择项目场景");
      document.getElementById("ws-scenario")?.focus();
      return;
    }

    const descriptionParts = [meta.projectCode.trim(), meta.scenario.trim()].filter(Boolean);
    const description = descriptionParts.length ? descriptionParts.join(" · ") : "";

    const payload: WorkspaceProjectCreatePayload = {
      name: trimmedName,
      description,
      workspaceMeta: {
        ...meta,
        projectCode: meta.projectCode.trim(),
        bidCode: meta.bidCode.trim(),
        scenario: meta.scenario.trim(),
        scale: meta.scale.trim(),
        startDate: meta.startDate,
        datacenterReadyDate: meta.datacenterReadyDate,
        deliveryFeatures: [...meta.deliveryFeatures],
        language: meta.language,
        owner: meta.owner.trim(),
        group: meta.group.trim(),
      },
    };

    setBusy(true);
    setError(null);
    try {
      await onCreate(payload);
      onDismiss();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [name, meta, onCreate, onDismiss]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-6"
      aria-modal="true"
      role="dialog"
      aria-labelledby={titleId}
    >
      <button
        type="button"
        aria-label="关闭"
        className="absolute inset-0 bg-black/55 backdrop-blur-[3px]"
        onClick={() => !busy && onDismiss()}
      />
      <div
        className={[
          "relative z-10 flex w-full flex-col overflow-hidden rounded-2xl border border-[var(--border-subtle)]",
          "bg-[var(--surface-1)] shadow-[0_24px_80px_rgba(0,0,0,0.45)] ring-1 ring-black/5 dark:ring-white/10",
          "max-h-[min(90dvh,36rem)] max-w-[min(calc(100vw-1.5rem),36rem)] sm:max-w-xl",
        ].join(" ")}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <FolderPlus size={17} className="shrink-0 text-[var(--accent)]" aria-hidden />
            <h2 id={titleId} className="truncate text-base font-semibold ui-text-primary">
              新建项目
            </h2>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={onDismiss}
            className="shrink-0 rounded-lg p-1.5 ui-text-muted transition-colors hover:bg-[var(--surface-2)] hover:ui-text-primary disabled:opacity-50"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-gutter:stable] px-4 py-4 sm:px-5 sm:py-5">
          <div className="space-y-5">
            <div>
              <label className={labelClass} htmlFor="new-ws-project-name">
                项目名称 <span className="text-red-500 dark:text-red-400">*</span>
              </label>
              <input
                id="new-ws-project-name"
                ref={nameRef}
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setError(null);
                }}
                disabled={busy}
                autoComplete="off"
                className={inputClass}
              />
            </div>
            <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
              <div>
                <label className={labelClass} htmlFor="ws-project-code">
                  项目编码 <span className="text-red-500 dark:text-red-400">*</span>
                </label>
                <input
                  id="ws-project-code"
                  type="text"
                  value={meta.projectCode}
                  onChange={(e) => {
                    setMeta((m) => ({ ...m, projectCode: e.target.value }));
                    setError(null);
                  }}
                  disabled={busy}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="ws-bid-code">
                  投标编码
                </label>
                <input
                  id="ws-bid-code"
                  type="text"
                  value={meta.bidCode}
                  onChange={(e) => setMeta((m) => ({ ...m, bidCode: e.target.value }))}
                  disabled={busy}
                  className={inputClass}
                />
              </div>
            </div>
            <div>
              <label className={labelClass} htmlFor="ws-scenario">
                项目场景 <span className="text-red-500 dark:text-red-400">*</span>
              </label>
              <NativeSelectWithChevron
                id="ws-scenario"
                value={meta.scenario}
                disabled={busy}
                onChange={(e) => {
                  setMeta((m) => ({ ...m, scenario: e.target.value }));
                  setError(null);
                }}
              >
                <option value="">请选择</option>
                {SCENARIO_SELECT_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </NativeSelectWithChevron>
            </div>
            <div>
              <label className={labelClass} htmlFor="ws-scale">
                项目规模
              </label>
              <NativeSelectWithChevron
                id="ws-scale"
                value={meta.scale}
                disabled={busy}
                onChange={(e) => setMeta((m) => ({ ...m, scale: e.target.value }))}
              >
                <option value="">请选择</option>
                {SCALE_SELECT_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </NativeSelectWithChevron>
            </div>
            <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
              <div>
                <label className={labelClass} htmlFor="ws-start">
                  项目开始时间 <span className="text-red-500 dark:text-red-400">*</span>
                </label>
                <input
                  id="ws-start"
                  type="date"
                  value={meta.startDate}
                  onChange={(e) => {
                    setMeta((m) => ({ ...m, startDate: e.target.value }));
                    setError(null);
                  }}
                  disabled={busy}
                  className={dateInputClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="ws-dc-ready">
                  机房改造完成时间 <span className="text-red-500 dark:text-red-400">*</span>
                </label>
                <input
                  id="ws-dc-ready"
                  type="date"
                  value={meta.datacenterReadyDate}
                  onChange={(e) => {
                    setMeta((m) => ({ ...m, datacenterReadyDate: e.target.value }));
                    setError(null);
                  }}
                  disabled={busy}
                  className={dateInputClass}
                />
              </div>
            </div>
            <fieldset id="ws-delivery-fieldset" className="min-w-0 border-0 p-0" tabIndex={-1}>
              <legend className={labelClass}>
                交付特点 <span className="text-red-500 dark:text-red-400">*</span>
              </legend>
              <div className="flex flex-wrap gap-x-2 gap-y-3">
                {DELIVERY_FEATURE_OPTIONS.map((opt) => {
                  const on = meta.deliveryFeatures.includes(opt);
                  return (
                    <button
                      key={opt}
                      type="button"
                      disabled={busy}
                      aria-pressed={on}
                      onClick={() => toggleDelivery(opt)}
                      className={
                        CHIP_OPTION_BASE +
                        (on
                          ? "border-[color-mix(in_srgb,var(--accent)_45%,transparent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-[var(--accent)]"
                          : chipInactive)
                      }
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset id="ws-lang-group" className="min-w-0 border-0 p-0" tabIndex={-1}>
              <legend className={labelClass}>
                项目语言 <span className="text-red-500 dark:text-red-400">*</span>
              </legend>
              <div className="flex flex-wrap gap-x-2 gap-y-3" role="radiogroup" aria-label="项目语言">
                {(
                  [
                    { v: "zh" as const, label: "中文" },
                    { v: "en" as const, label: "英文" },
                  ] as const
                ).map(({ v, label }) => (
                  <button
                    key={v}
                    type="button"
                    role="radio"
                    aria-checked={meta.language === v}
                    disabled={busy}
                    onClick={() => {
                      setMeta((m) => ({ ...m, language: v }));
                      setError(null);
                    }}
                    className={
                      CHIP_OPTION_BASE +
                      (meta.language === v
                        ? "border-[color-mix(in_srgb,var(--accent)_45%,transparent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-[var(--accent)]"
                        : chipInactive)
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            </fieldset>

            <div>
              <label className={labelClass} htmlFor="ws-owner">
                项目负责人
              </label>
              <input
                id="ws-owner"
                type="text"
                value={meta.owner}
                onChange={(e) => setMeta((m) => ({ ...m, owner: e.target.value }))}
                disabled={busy}
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="ws-group">
                项目群
              </label>
              <NativeSelectWithChevron
                id="ws-group"
                value={meta.group}
                disabled={busy}
                onChange={(e) => setMeta((m) => ({ ...m, group: e.target.value }))}
              >
                <option value="">请选择</option>
                {GROUP_SELECT_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </NativeSelectWithChevron>
            </div>
          </div>

          {error ? (
            <p
              className="mt-5 rounded-md border-l-2 border-amber-500 bg-amber-500/[0.08] py-2.5 pl-3 pr-2 text-xs leading-snug text-amber-800 dark:border-amber-500/80 dark:bg-amber-500/10 dark:text-amber-200/95"
              role="alert"
            >
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-[var(--border-subtle)] bg-[color-mix(in_oklab,var(--surface-2)_40%,transparent)] px-4 py-3 supports-[backdrop-filter]:backdrop-blur-sm sm:px-5">
          <button
            type="button"
            disabled={busy}
            onClick={onDismiss}
            className="min-h-[2.5rem] rounded-full border border-[var(--border-subtle)] px-5 py-2 text-xs ui-text-muted transition-colors hover:bg-[var(--surface-2)] hover:ui-text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit()}
            className="min-h-[2.5rem] rounded-full border border-[color-mix(in_srgb,var(--accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] px-5 py-2 text-xs font-medium text-[var(--accent)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent)_22%,transparent)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "创建中…" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
