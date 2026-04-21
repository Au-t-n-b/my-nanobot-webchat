"use client";

import { RemoteBrowser } from "@/components/RemoteBrowser";
import type { BaseRendererProps } from "../previewTypes";

export function BrowserRenderer(props: BaseRendererProps & { onClosePanel?: () => void }) {
  return <RemoteBrowser filePath={props.path} onClosePanel={props.onClosePanel} />;
}

