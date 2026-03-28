"use client";

const MODELS = ["glm-4", "glm-4v", "glm-4.7"] as const;

export type AvailableModel = (typeof MODELS)[number];

type Props = {
  value: AvailableModel;
  onChange: (model: AvailableModel) => void;
};

export function ModelSelector({ value, onChange }: Props) {
  return (
    <label className="inline-flex items-center gap-2 text-xs ui-text-secondary">
      <span>模型</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as AvailableModel)}
        className="rounded-lg border px-2 py-1 text-xs"
        style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
        aria-label="选择模型"
      >
        {MODELS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </label>
  );
}
