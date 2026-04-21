"use client";

import type { BaseRendererProps } from "../previewTypes";

export function HtmlRenderer(props: BaseRendererProps & { html: string }) {
  return (
    <div
      className="max-w-none text-sm ui-text-primary p-3 rounded-xl border border-[var(--border-subtle)] dark:border-white/10 bg-[var(--surface-2)] dark:bg-black/35 dark:shadow-inner [&_a]:ui-link [&_p]:mb-2"
      dangerouslySetInnerHTML={{ __html: props.html }}
    />
  );
}

