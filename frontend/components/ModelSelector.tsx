"use client";

// Model options come from config (agents.models) so the dropdown matches the
// user's provider and "common models" list. The current value is always shown.

type Props = {
  value: string;
  onChange: (model: string) => void;
  models?: string[];
  compact?: boolean;
  /** 追加到 `<select>` 的 class（如工具栏毛玻璃容器内半透明背景） */
  selectClassName?: string;
};

export function ModelSelector({ value, onChange, models, compact = false, selectClassName = "" }: Props) {
  const extra = (models ?? [])
    .map((m) => (typeof m === "string" ? m.trim() : ""))
    .filter((m) => m);
  const options = Array.from(new Set([...extra]));

  // If the current value is not a preset (e.g. set from config), show it as an
  // additional option at the top so the dropdown is consistent.
  const showExtra = value && !options.includes(value);

  return (
    <label className="inline-flex items-center gap-2 text-xs ui-text-secondary">
      {!compact && <span className="whitespace-nowrap">模型</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--text-primary)] ${selectClassName}`.trim()}
        aria-label="选择模型"
      >
        {showExtra && (
          <option key="__extra__" value={value}>
            {value}
          </option>
        )}
        {options.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </label>
  );
}
