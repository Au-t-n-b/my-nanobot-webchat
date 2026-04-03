"use client";

type Props = {
  title?: string | null;
  value?: string | number | null;
};

export function SduiStatistic({ title, value }: Props) {
  const v = value === null || value === undefined ? "" : value;
  return (
    <div className="min-w-0">
      <div className="text-sm font-medium text-slate-500 mb-1 dark:text-zinc-400">{title ?? ""}</div>
      <div className="text-2xl font-bold tracking-tight text-slate-900 tabular-nums dark:text-zinc-100">{v}</div>
    </div>
  );
}
