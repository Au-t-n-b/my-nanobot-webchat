"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import type { BaseRendererProps } from "../previewTypes";

function ImageEmbed({ url, path }: { url: string; path: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(path).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex flex-col items-center gap-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="" className="max-w-full object-contain mx-auto" />
      <button
        type="button"
        onClick={copy}
        aria-label="复制文件路径"
        className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-xs ui-text-secondary hover:bg-[var(--surface-3)] transition-colors"
      >
        {copied ? <Check size={10} /> : <Copy size={10} />}
        {copied ? "已复制路径" : "复制路径"}
      </button>
    </div>
  );
}

export function EmbedRenderer(props: BaseRendererProps & { embedKind: "image" | "pdf" | "html" }) {
  const url = props.url;
  if (!url) return null;

  if (props.embedKind === "image") return <ImageEmbed url={url} path={props.path} />;

  return (
    <div className="rounded-xl border border-black/[0.06] dark:border-white/10 bg-slate-100/90 dark:bg-black/40 p-2 shadow-inner overflow-hidden">
      <iframe
        title="preview"
        src={url}
        className="w-full min-h-[500px] rounded-lg border border-black/[0.08] dark:border-white/10 bg-white"
      />
    </div>
  );
}

