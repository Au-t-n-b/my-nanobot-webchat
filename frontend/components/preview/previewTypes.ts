import type { PreviewKind } from "@/lib/previewKind";

export type PreviewFetchMode = "none" | "text" | "arrayBuffer";

export type PreviewResolution = {
  /** 原始输入路径（workspace 相对路径 / browser:// / skill-ui:// 等） */
  path: string;
  kind: PreviewKind;
  /** 对应的 `/api/file?path=...`，仅当是文件类预览且需要 URL 时给出 */
  url?: string;
  /**
   * 壳层应如何预取内容（严格收敛：renderers 不允许 fetch）
   * - none: 不需要预取（例如 image/pdf/html iframe / browser:// / skill-ui://）
   * - text: 需要 `fetch(url).text()`
   * - arrayBuffer: 需要 `fetch(url).arrayBuffer()`
   */
  fetch: PreviewFetchMode;
};

export type PreviewContent = string | ArrayBuffer;

export interface ParserContext {
  initialBuffer?: ArrayBuffer;
}

// 输入：Resolver 给出的元数据；输出：Renderer 需要的核心数据（解析后的 payload）
export type PreviewParser<T = unknown> = (
  resolution: PreviewResolution,
  context?: ParserContext,
) => Promise<T>;

export interface BaseRendererProps {
  path: string;
  resolution: PreviewResolution;
  /** 壳层预取好的内容（需要转换/解析的格式走这里） */
  content?: PreviewContent;
  /** iframe / img / download 等直接使用 */
  url?: string;
  /** 预留：Phase 2+ renderer 触发交互动作 */
  onAction?: (action: string, payload: unknown) => void;
}

