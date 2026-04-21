import { buildProxiedFileUrl } from "@/lib/apiFile";
import { previewKindFromPath } from "@/lib/previewKind";
import type { PreviewResolution } from "./previewTypes";

/**
 * 纯函数解析器：相同 path => 相同 resolution。
 * 注意：此处不做 fetch / 不读全局状态 / 不做副作用。
 */
export function resolvePreview(path: string): PreviewResolution {
  const kind = previewKindFromPath(path);

  // 非文件类（不需要 /api/file）
  if (kind === "browser" || kind === "skill-ui") {
    return { path, kind, fetch: "none" };
  }

  const url = buildProxiedFileUrl(path);

  if (kind === "binary") return { path, kind, url, fetch: "none" };
  if (kind === "image" || kind === "pdf" || kind === "html") return { path, kind, url, fetch: "none" };

  if (kind === "xlsx" || kind === "docx" || kind === "zip") return { path, kind, url, fetch: "arrayBuffer" };
  // md / mermaid / text
  return { path, kind, url, fetch: "text" };
}

