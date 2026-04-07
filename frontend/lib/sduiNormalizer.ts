/**
 * 兼容旧版 / 不规范 SDUI JSON：将嵌套的 `props` 合并到节点顶层，再递归处理 `children`。
 * 合并策略：顶层已有且非 undefined 的键不被 props 覆盖（优先保留扁平字段）。
 * 整份文档递归剥离呈现类非法键（className/style/styles/css）；开发环境 console.warn。
 * 节点层再将历史数字 gap 规范为 SpacingToken。
 */

import { SDUI_NODE_TYPE_VALUES, SPACING_TOKENS } from "@/lib/sdui";
import { isIllegalPresentationKey, warnIllegalPresentationField } from "@/lib/sduiCompliance";
import { coerceLegacyGapToToken } from "@/lib/sduiTokens";

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function isSpacingTokenString(s: string): boolean {
  return (SPACING_TOKENS as readonly string[]).includes(s);
}

function normalizeLayoutGapField(n: Record<string, unknown>): void {
  const t = n.type;
  if (t !== "Stack" && t !== "Row") return;
  const g = n.gap;
  if (g === undefined) return;
  if (typeof g === "string" && isSpacingTokenString(g)) return;
  const coerced = coerceLegacyGapToToken(g);
  if (coerced !== undefined) n.gap = coerced;
  else delete n.gap;
}

function coerceLayoutGapOnly(n: Record<string, unknown>): void {
  normalizeLayoutGapField(n);
}

/** 将 `type` 纠正为协议中的 PascalCase（兼容大小写漂移，避免落入 UnknownNode） */
function canonicalizeNodeTypeInPlace(n: Record<string, unknown>): void {
  const t = n.type;
  if (typeof t !== "string" || !t.length) return;
  if ((SDUI_NODE_TYPE_VALUES as readonly string[]).includes(t)) return;
  const lower = t.toLowerCase();
  const found = SDUI_NODE_TYPE_VALUES.find((k) => k.toLowerCase() === lower);
  if (found) n.type = found;
}

/**
 * 深度遍历整棵 JSON（含 `meta`、`DataGrid.rows` 等），删除呈现类非法键；
 * 开发环境下对每个被删除的键调用 warnIllegalPresentationField。
 */
export function deepStripIllegalPresentationKeysInPlace(value: unknown): void {
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) {
    for (const item of value) deepStripIllegalPresentationKeysInPlace(item);
    return;
  }
  const obj = value as Record<string, unknown>;
  for (const key of Object.keys(obj)) {
    if (isIllegalPresentationKey(key)) {
      warnIllegalPresentationField(key);
      delete obj[key];
    }
  }
  for (const key of Object.keys(obj)) {
    deepStripIllegalPresentationKeysInPlace(obj[key]);
  }
}

/**
 * 递归规范化单个节点；非对象原样返回。
 */
export function normalizeSduiNode(raw: unknown): unknown {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    return raw;
  }

  const n: Record<string, unknown> = { ...(raw as Record<string, unknown>) };
  canonicalizeNodeTypeInPlace(n);
  const props = n.props;

  if (isRecord(props)) {
    for (const [k, v] of Object.entries(props)) {
      if (!(k in n) || n[k] === undefined) {
        n[k] = v;
      }
    }
    delete n.props;
  }

  const ch = n.children;
  if (Array.isArray(ch)) {
    n.children = ch.map((c) => normalizeSduiNode(c));
  }

  if (n.type === "Tabs" && Array.isArray(n.tabs)) {
    n.tabs = n.tabs.map((tab) => {
      if (!isRecord(tab)) return tab;
      const panel: Record<string, unknown> = { ...tab };
      const pch = panel.children;
      if (Array.isArray(pch)) {
        panel.children = pch.map((c) => normalizeSduiNode(c));
      }
      return panel;
    });
  }

  coerceLayoutGapOnly(n);
  return n;
}

/**
 * 规范化整份文档（根对象）：处理 `root`，并可选补全 `type: "SduiDocument"`。
 */
export function normalizeSduiDocumentInput(data: unknown): unknown {
  if (!isRecord(data)) {
    return data;
  }

  const out: Record<string, unknown> = { ...data };

  deepStripIllegalPresentationKeysInPlace(out);

  if (out.root !== undefined) {
    out.root = normalizeSduiNode(out.root);
  }

  if (out.type === undefined) {
    out.type = "SduiDocument";
  }

  return out;
}
