/**
 * 冷启路径（v0.4 起：Skill-First 主路径）：
 *   - 直接给 `/api/chat` 发一条 `chat_card_intent` JSON（type=chat_card_intent / verb=skill_runtime_start），
 *     由后端 fast-path 路由到 `project_guide` 的 `runtime/driver.py`；
 *   - driver 自己读 `phases.json` + `task_progress.json` + `registry/*.json`，调
 *     `phase_rules.decide_branch`，发出 `chat.guidance` 事件 → 前端渲染 `GuidanceCard`；
 *   - **完全绕过 LLM**：解决了 v0.3 由模型解释 SKILL.md 时偶发的"不读 registry / 流式中断 / 路径理解错"等问题。
 *
 * 旧 LLM 路径（`buildProjectGuideColdStartUserPrompt`）保留作为兜底入口，便于退回调试，
 * 但不再是冷启动 effect 的默认调用。
 */
export const PROJECT_GUIDE_SKILL_ID = "project_guide";

const STORAGE_PREFIX = "nanobot:projectGuideColdStart:";

/** 本 thread 冷启动已成功完成，不再发 */
export const PROJECT_GUIDE_COLD_START_OK = "1";
/** 本 thread 已尝试但失败/放弃，避免 effect 因依赖抖动反复请求导致界面闪动 */
export const PROJECT_GUIDE_COLD_START_DONE_BAD = "0";

export function projectGuideColdStartStorageKey(threadId: string): string {
  return `${STORAGE_PREFIX}${(threadId || "").trim()}`;
}

export function isProjectGuideColdStartSettled(raw: string | null): boolean {
  return raw === PROJECT_GUIDE_COLD_START_OK || raw === PROJECT_GUIDE_COLD_START_DONE_BAD;
}

/**
 * Skill-First 冷启 intent。`requestId` 含 `threadId` 以便后端 nonce 化时仍能从日志反查。
 *
 * 注意：当前 `dispatch_skill_runtime_intent` 的 `skill_runtime_start` 分支会以 `result={}`
 * 调 driver，未透传 `userId/workId`；driver 会按 `users.lastLoginAt` 兜底锁定用户。
 * 若日后改为透传，driver 已支持读 `result.userId/result.workId`，本函数也已预先把它们塞到 payload。
 */
export function buildProjectGuideColdStartIntent(args: {
  threadId: string;
  userId?: string;
  workId?: string;
}): string {
  const tid = (args.threadId || "").trim();
  const intent = {
    type: "chat_card_intent" as const,
    verb: "skill_runtime_start" as const,
    payload: {
      type: "skill_runtime_start" as const,
      skillName: PROJECT_GUIDE_SKILL_ID,
      requestId: `req-cold:${tid || "unknown"}`,
      action: "cold_start",
      threadId: tid,
      ...(args.userId ? { userId: args.userId } : {}),
      ...(args.workId ? { workId: args.workId } : {}),
    },
  };
  return JSON.stringify(intent);
}

/**
 * @deprecated v0.4 起改用 {@link buildProjectGuideColdStartIntent}。
 * 仅保留以便退回 LLM 路径调试。
 */
export function buildProjectGuideColdStartUserPrompt(): string {
  return [
    "[系统任务-冷启动-勿向用户原样展示本段]",
    "请按工作区 **skills/project_guide/SKILL.md** 中的「## 冷启动（Cold start / Agent）」节执行。",
    "1）用 read_file 读该文件（若路径不在预期，可先用 list_dir 从工作区根查找 skills/）。",
    "2）严格按文内要求用中文向用户做简短引导（1～3 句），可说明当前建议关注的阶段或下一步。",
    "3）仅在文档或系统允许范围内调用工具；不要编造项目进展。",
    "4）未读到文件时，简要说明并建议检查 .nanobot/workspace/skills 下是否已部署 project_guide。",
  ].join("\n");
}
