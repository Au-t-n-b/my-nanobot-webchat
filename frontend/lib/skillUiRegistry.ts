/**
 * Skill UI：合成路径 `skill-ui://ComponentName?dataFile=...` 与注册表。
 * Agent 可输出 `[RENDER_UI](skill-ui://...)`，由右栏拉取 JSON 后注入组件。
 */

import type { ComponentType } from "react";

import { SduiView } from "@/components/skills/SduiView";

/** 右栏 synthetic path 的 scheme，与 previewKind「skill-ui」对应 */
export const SKILL_UI_SCHEME = "skill-ui://" as const;

export type ParsedSkillUiUri = {
  /** 注册表中的顶层外壳名，SDUI 固定为 SduiView */
  component: string;
  /** 供 GET /api/file?path= 使用的路径 */
  dataFile: string | null;
  rawSearchParams: Record<string, string>;
};

/**
 * 解析 `skill-ui://SduiView?dataFile=path/to/data.json`
 * 组件名允许 URL 编码；dataFile 支持 encodeURIComponent。
 */
export function parseSkillUiPath(path: string): ParsedSkillUiUri | null {
  const trimmed = path.trim();
  if (!trimmed.toLowerCase().startsWith("skill-ui://")) return null;

  let url: URL;
  try {
    url = new URL(trimmed.replace(/^skill-ui:\/\//i, "http://skill-ui/"));
  } catch {
    return null;
  }

  const hostPart = trimmed.slice("skill-ui://".length).split(/[?#]/)[0] ?? "";
  const component = decodeURIComponent(hostPart.replace(/^\/*/, "").split("/")[0] ?? "").trim();
  if (!component) return null;

  const dataFileRaw = url.searchParams.get("dataFile");
  const dataFile = dataFileRaw
    ? decodeURIComponent(dataFileRaw.replace(/\+/g, " "))
    : null;

  const rawSearchParams: Record<string, string> = {};
  url.searchParams.forEach((v, k) => {
    rawSearchParams[k] = v;
  });

  return { component, dataFile, rawSearchParams };
}

/**
 * 大模块看板（Base Layer）命名约定（Convention）：
 * - `skill-ui://…?dataFile=…` 中，路径（不区分大小写）**包含**以下任一段即视为常驻大盘，路由到右栏底层：
 *   - `-master/data/dashboard.json`
 *   - `-pipeline/data/dashboard.json`
 * - 其余 `skill-ui`（如各 Step 的 `ui.json`）与文件 / 浏览器预览 → Overlay Layer。
 */
export function isBaseLayerDashboardSkillUi(path: string): boolean {
  if (!path.trim().toLowerCase().startsWith("skill-ui://")) return false;
  const p = parseSkillUiPath(path);
  const df = (p?.dataFile ?? "").toLowerCase().replace(/\\/g, "/");
  if (!df) return false;
  return (
    df.includes("-master/data/dashboard.json") ||
    df.includes("-pipeline/data/dashboard.json")
  );
}

/** @deprecated 请改用 {@link isBaseLayerDashboardSkillUi}（语义相同，名称更准确） */
export function isPipelineDashboardSkillUi(path: string): boolean {
  return isBaseLayerDashboardSkillUi(path);
}

/**
 * 强阻断 Action SDUI：非大盘约定的 `skill-ui`（如各 Step 的 ui.json）。
 * 必须全幅盖在业务视窗之上，不可收入 Tab。
 */
export function isBlockingActionSkillUi(path: string): boolean {
  if (!path.trim().toLowerCase().startsWith("skill-ui://")) return false;
  return !isBaseLayerDashboardSkillUi(path);
}

/** 构造供 openFilePreview 使用的 synthetic path */
export function buildSkillUiPreviewPath(
  component: string,
  options: { dataFile?: string | null } = {}
): string {
  const name = component.trim();
  if (!name) throw new Error("skill-ui: empty component name");
  const q = new URLSearchParams();
  if (options.dataFile != null && options.dataFile !== "") {
    q.set("dataFile", options.dataFile);
  }
  const qs = q.toString();
  const enc = encodeURIComponent(name);
  return qs ? `${SKILL_UI_SCHEME}${enc}?${qs}` : `${SKILL_UI_SCHEME}${enc}`;
}

export type SkillUiDataProps<T = unknown> = {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  dataFilePath: string | null;
};

export type SkillUiComponentProps<T = unknown> = SkillUiDataProps<T>;

export type SkillUiRegistryMap = Record<string, ComponentType<SkillUiComponentProps>>;

/** 顶层 Skill UI 外壳：SDUI 固定为 SduiView，内部由 JSON root 递归渲染 */
export const SKILL_UI_REGISTRY: SkillUiRegistryMap = {
  SduiView,
};
