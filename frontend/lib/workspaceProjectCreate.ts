/** 新建工作区项目表单（本地 nanobot 仅作类型与选项；不与 Gantt API 绑定） */

export const DELIVERY_FEATURE_OPTIONS = [
  "风冷",
  "液冷",
  "新增",
  "节点扩容",
  "推理",
  "训练",
  "训推",
  "大EP",
  "灵衢",
  "A2",
  "A3",
] as const;

export type ProjectLanguage = "zh" | "en";

export const SCENARIO_SELECT_OPTIONS: string[] = ["场景一", "场景二", "场景三"];
export const SCALE_SELECT_OPTIONS: string[] = ["规模一", "规模二", "规模三"];
export const GROUP_SELECT_OPTIONS: string[] = ["群聊一", "群聊二", "群聊三"];

export type WorkspaceProjectFormMeta = {
  projectCode: string;
  bidCode: string;
  scenario: string;
  scale: string;
  startDate: string;
  datacenterReadyDate: string;
  deliveryFeatures: string[];
  /** 表单内可为空以强制选择；提交前须为 zh | en */
  language: "" | ProjectLanguage;
  owner: string;
  group: string;
};

export type WorkspaceProjectCreatePayload = {
  name: string;
  description: string;
  workspaceMeta: Omit<WorkspaceProjectFormMeta, "language"> & { language: ProjectLanguage };
};

export function emptyWorkspaceProjectFormMeta(): WorkspaceProjectFormMeta {
  return {
    projectCode: "",
    bidCode: "",
    scenario: "",
    scale: "",
    startDate: "",
    datacenterReadyDate: "",
    deliveryFeatures: [],
    language: "",
    owner: "",
    group: "",
  };
}
