/** 账号 / 项目 / 登出等导致「会话存储命名空间」变化时派发 */
export const WORKBENCH_SCOPE_CHANGED_EVENT = "nanobot-workbench-scope-changed";

export function bumpWorkbenchStorageScope(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(WORKBENCH_SCOPE_CHANGED_EVENT));
}

export function sanitizeStorageSegment(s: string): string {
  return s.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "x";
}

/** accountId + 工作区项目 id → 与本地会话相关的命名空间段（不含 chat key 前缀） */
export function chatStorageScopeFromParts(accountId: string, workspaceProjectId: string): string {
  const a = sanitizeStorageSegment(accountId);
  const p = workspaceProjectId.trim() ? sanitizeStorageSegment(workspaceProjectId) : "_noproject";
  return `${a}__${p}`;
}
