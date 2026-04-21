"use client";

import { FileQuestion } from "lucide-react";
import type { BaseRendererProps } from "../previewTypes";

export function BinaryRenderer(props: BaseRendererProps & { name: string }) {
  if (!props.url) return null;
  return (
    <div className="text-sm ui-text-secondary flex flex-col gap-3 items-start">
      <FileQuestion size={32} className="ui-text-muted" />
      <p>无法内联预览此类型，可通过下方链接下载。</p>
      <a href={props.url} download={props.name} className="ui-btn-accent rounded-md px-3 py-1.5">
        打开 / 下载 {props.name}
      </a>
    </div>
  );
}

