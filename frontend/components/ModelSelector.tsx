"use client";

// Model options come from config (agents.models) so the dropdown matches the
// user's provider and "common models" list. The current value is always shown.

type Props = {
  value: string;
  onChange: (model: string) => void;
  models?: string[];
  compact?: boolean;
};

export function ModelSelector({ value, onChange, models, compact = false }: Props) {
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
        className="rounded-lg border px-2 py-1 text-xs"
        style={{
          borderColor: "var(--border-subtle)",
          background: "var(--surface-2)",
          color: "var(--text-primary)",
        }}
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
