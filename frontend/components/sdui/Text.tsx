"use client";

type Props = {
  content?: string | null;
  variant?: "title" | "body" | "muted" | "mono";
};

const variantClass: Record<NonNullable<Props["variant"]>, string> = {
  title: "text-base font-semibold tracking-tight text-slate-900",
  body: "text-sm leading-relaxed text-slate-700",
  muted: "text-sm text-slate-400",
  mono: "text-[13px] font-mono text-slate-500 bg-slate-50 px-1 py-0.5 rounded",
};

export function SduiText({ content, variant = "body" }: Props) {
  return (
    <p className={`${variantClass[variant] ?? variantClass.body} whitespace-pre-wrap`.trim()}>
      {content ?? ""}
    </p>
  );
}
