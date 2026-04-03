/**
 * SDUI 禁止由生成侧控制的呈现类键；与 docs/sdui-protocol-spec.md §1.2、§6.3 一致。
 */

export const SDUI_ILLEGAL_PRESENTATION_KEYS = ["className", "style", "styles", "css"] as const;

const ILLEGAL_SET = new Set<string>(SDUI_ILLEGAL_PRESENTATION_KEYS);

export function isIllegalPresentationKey(key: string): boolean {
  return ILLEGAL_SET.has(key);
}

/**
 * 开发环境下：发现非法键时告警（剥离逻辑在 sduiNormalizer 中执行）。
 */
export function warnIllegalPresentationField(field: string): void {
  if (process.env.NODE_ENV !== "development") return;
  if (!isIllegalPresentationKey(field)) return;
  console.warn(
    `⚠️ 检测到非法字段 [${field}]：SDUI 严禁生成侧控制样式。请参考 docs/sdui-protocol-spec.md 修正 Skill 输出。`,
  );
}

/**
 * 只读遍历：用于未经过 `normalizeSduiDocumentInput` 的 payload，在 `parseSduiDocument` 前提示合规问题。
 * 若已先 normalize，树上应已无非法键，本函数不会产生重复告警。
 */
export function scanIllegalPresentationKeysForDev(value: unknown): void {
  if (process.env.NODE_ENV !== "development") return;
  const visit = (v: unknown): void => {
    if (v === null || typeof v !== "object") return;
    if (Array.isArray(v)) {
      for (const item of v) visit(item);
      return;
    }
    const obj = v as Record<string, unknown>;
    for (const key of Object.keys(obj)) {
      if (isIllegalPresentationKey(key)) {
        warnIllegalPresentationField(key);
      }
      visit(obj[key]);
    }
  };
  visit(value);
}
