/**
 * Skill-First 混合模式：受控 Agent 子任务（与后端 `skill.agent_task_execute` 对齐）。
 * 详细字段见仓库 `docs/hybrid-mode-protocol.md`。
 */

import type { TaskStatusPayload } from "@/hooks/useAgentChat";

export type SkillAgentTaskResultDelivery = "dashboard" | "sse";

/** driver → stdout → bridge 的 `payload` 最小类型（前端构建/阅读用） */
export type SkillAgentTaskExecutePayload = {
  taskId: string;
  parentRequestId?: string;
  skillName?: string;
  stepId: string;
  goal: string;
  allowedTools?: string[];
  maxIterations?: number;
  resultSchema?: { type: string; [key: string]: unknown };
  /** 默认 dashboard；预览洞察等临时 JSON 必须用 sse（与后端一致） */
  resultDelivery?: SkillAgentTaskResultDelivery;
  /** dashboard 投递时必填；sse 模式下省略 */
  syntheticPath?: string;
  docId?: string;
  summaryNodeId?: string;
};

/** 供前端或测试构造 `skill_runtime_event` 的 envelope（verb 为 skill_runtime_event 时 payload 即此对象）。 */
export function buildSkillAgentTaskExecuteEnvelope(args: {
  threadId: string;
  skillName: string;
  skillRunId: string;
  payload: SkillAgentTaskExecutePayload;
  timestamp?: number;
}): {
  event: "skill.agent_task_execute";
  threadId: string;
  skillName: string;
  skillRunId: string;
  timestamp: number;
  payload: SkillAgentTaskExecutePayload;
} {
  return {
    event: "skill.agent_task_execute",
    threadId: args.threadId,
    skillName: args.skillName,
    skillRunId: args.skillRunId,
    timestamp: args.timestamp ?? Date.now(),
    payload: args.payload,
  };
}

/**
 * 从最近一次 TaskStatusUpdate 推断「混合模式子任务」一行提示（模块 id 以 `hybrid:` 开头）。
 */
export function hybridSubtaskHintFromTaskStatus(task: TaskStatusPayload | null): string | null {
  if (!task?.modules?.length) return null;
  const hybridMods = task.modules.filter((m) => String(m.id).startsWith("hybrid:"));
  if (!hybridMods.length) return null;
  const running = hybridMods.find((m) => m.status === "running");
  const mod = running ?? hybridMods[hybridMods.length - 1];
  const step = mod.steps?.[0];
  const stepName = step?.name?.trim();
  if (mod.status === "running") {
    return `Agent 子任务进行中${stepName ? `：${stepName}` : ""}`;
  }
  if (mod.status === "failed") {
    return `Agent 子任务失败${stepName ? `：${stepName}` : ""}`;
  }
  if (mod.status === "skipped") {
    return `Agent 子任务已跳过${stepName ? `：${stepName}` : ""}`;
  }
  return `Agent 子任务${stepName ? `：${stepName}` : "已完成"}`;
}
