/**
 * Skill UI：合成路径 `skill-ui://ComponentName?dataFile=...` 与注册表。
 * Agent 可输出 `[RENDER_UI](skill-ui://...)`，由右栏拉取 JSON 后注入组件。
 */

import type { ComponentType } from "react";

import { SurveySummary } from "@/components/skills/SurveySummary";

/** 右栏 synthetic path 的 scheme，与 previewKind「skill-ui」对应 */
export const SKILL_UI_SCHEME = "skill-ui://" as const;

export type ParsedSkillUiUri = {
  /** 注册表中的组件名，如 SurveySummary */
  component: string;
  /** 供 GET /api/file?path= 使用的路径 */
  dataFile: string | null;
  rawSearchParams: Record<string, string>;
};

/**
 * 解析 `skill-ui://SurveySummary?dataFile=path/to/data.json`
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

/** 内置注册的 Skill UI 组件（可继续在此追加 import） */
export const SKILL_UI_REGISTRY: SkillUiRegistryMap = {
  SurveySummary,
};
