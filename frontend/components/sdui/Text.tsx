"use client";

type Props = {
  content?: string | null;
  variant?: "title" | "body" | "muted" | "mono";
};

const variantClass: Record<NonNullable<Props["variant"]>, string> = {
  title: "text-base font-semibold tracking-tight text-[var(--text-primary)]",
  body: "text-sm leading-relaxed text-[var(--text-secondary)]",
  muted: "text-sm text-[var(--text-muted)]",
  mono: "text-[13px] font-mono text-[var(--text-muted)] bg-[var(--surface-2)] px-1 py-0.5 rounded",
};

export function SduiText({ content, variant = "body" }: Props) {
  return (
    <p className={`${variantClass[variant] ?? variantClass.body} whitespace-pre-wrap`.trim()}>
      {content ?? ""}
    </p>
  );
}
