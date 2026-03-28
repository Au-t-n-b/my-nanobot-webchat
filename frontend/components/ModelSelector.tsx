"use client";

// Preset quick-pick options shown in the dropdown.
// If the config supplies a model not in this list it is shown as an extra option.
const PRESET_MODELS = ["glm-4", "glm-4v", "glm-4.7"] as const;
export type AvailableModel = (typeof PRESET_MODELS)[number];

type Props = {
  value: string;
  onChange: (model: string) => void;
};

export function ModelSelector({ value, onChange }: Props) {
  // If the current value is not a preset (e.g. set from config), show it as an
  // additional option at the top so the dropdown is consistent.
  const showExtra = value && !(PRESET_MODELS as readonly string[]).includes(value);

  return (
    <label className="inline-flex items-center gap-2 text-xs ui-text-secondary">
      <span>模型</span>
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
        {PRESET_MODELS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </label>
  );
}
