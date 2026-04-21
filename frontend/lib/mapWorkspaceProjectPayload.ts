import type { LocalProject } from "@/lib/localProjects";
import type { WorkspaceProjectCreatePayload } from "@/lib/workspaceProjectCreate";

/** 将新建项目弹窗 payload 映射为 createLocalProjectWithMeta 参数 */
export function workspacePayloadToLocalProjectMeta(
  p: WorkspaceProjectCreatePayload,
): Omit<LocalProject, "id" | "createdAt"> {
  const m = p.workspaceMeta;
  const stakeParts = [
    m.owner.trim() ? `负责人：${m.owner.trim()}` : "",
    m.startDate ? `开始：${m.startDate}` : "",
    m.datacenterReadyDate ? `机房就绪：${m.datacenterReadyDate}` : "",
  ].filter(Boolean);
  return {
    name: p.name.trim(),
    code: m.projectCode.trim(),
    bidCode: m.bidCode.trim(),
    scenario: m.scenario.trim(),
    scale: m.scale.trim(),
    deliveryFeatures: m.deliveryFeatures.join("、"),
    language: m.language,
    projectGroup: m.group.trim(),
    stakeholders: stakeParts.join("；"),
  };
}
