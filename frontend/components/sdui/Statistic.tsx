"use client";

type Props = {
  title?: string | null;
  value?: string | number | null;
};

export function SduiStatistic({ title, value }: Props) {
  const v = value === null || value === undefined ? "" : value;
  return (
    <div className="min-w-0 w-full text-center">
      <div className="mb-1 text-xs font-medium text-[var(--text-muted)]">{title ?? ""}</div>
      <div className="text-3xl font-bold tabular-nums tracking-tight text-[var(--text-primary)]">{v}</div>
    </div>
  );
}
