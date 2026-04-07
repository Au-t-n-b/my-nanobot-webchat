"use client";

type Props = {
  orientation?: "horizontal" | "vertical";
};

export function SduiDivider({ orientation = "horizontal" }: Props) {
  if (orientation === "vertical") {
    return <div className="my-0 self-stretch w-px bg-[var(--border-subtle)]" aria-hidden />;
  }
  return <hr className="my-2 h-px border-0 bg-[var(--border-subtle)]" aria-hidden />;
}
