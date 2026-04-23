/**
 * 冷启：对主 Agent 发**一条不可见 user 轮**（`showInTranscript: false`），
 * 同时 **`showAssistantInTranscript: true`** 以展示**助手**气泡与流式正文；
 * 由模型按 `skills/project_guide/SKILL.md` 执行冷启段落。不再以 `skill_runtime_start`
 * 为冷启主路径。
 *
 * 技能盘路径应与后端 `get_skills_root()` 一致（如 `%USERPROFILE%\.nanobot\workspace\skills`），
 * Agent 工作区需能 `read_file` 到本文件。
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
 * 静默冷启时作为 user 消息体发给 `/api/chat`；模型会按此任务读取 SKILL 并回复（助手可见）。
 * 与 ``sendSilentMessage`` 一致：showInTranscript: false。
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
