/**
 * 为 SDUI 递归列表生成稳定 React key：优先 node.id，否则基于节点内容摘要 + 父路径与下标保证同级唯一。
 */

import type { SduiNode } from "@/lib/sdui";

/** DJB2 哈希，输出短十六进制串 */
export function hashDjb2Hex(input: string): string {
  let h = 5381;
  for (let i = 0; i < input.length; i++) {
    h = (h * 33) ^ input.charCodeAt(i);
  }
  return (h >>> 0).toString(16);
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String((value as { type?: string })?.type ?? "node");
  }
}

/**
 * @param node - 子节点
 * @param index - 在父 children 中的下标（保证同级唯一）
 * @param parentKey - 父级路径前缀（如 root、root/n:a1b2:0）
 */
export function stableChildKey(node: SduiNode, index: number, parentKey: string): string {
  const rawId = (node as { id?: unknown }).id;
  if (typeof rawId === "string" && rawId.trim()) {
    // v3: When node.id is present, key must be globally stable so leaf patches
    // don't cause unmount/remount and so moving nodes doesn't reset state.
    return `id:${rawId.trim()}`;
  }
  const sig = safeStringify(node);
  const h = hashDjb2Hex(sig);
  return `${parentKey}/n:${h}:i:${index}`;
}
