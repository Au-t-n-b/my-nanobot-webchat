/**
 * 与「六段大流程」对齐的**候选**表（`taskProgressId` 与 `task_progress.json` 的 moduleId 一致）。
 * 在已有 ``/api/task-status`` 数据时，**顶部总进度条**以 `task_status`（`task_progress.json`）的 `modules`
 * 顺序/名称/子任务为唯一主数据；本表仅作无 `taskStatus` 时的回退、并与 module.json 做合并以提供 dashboard 数据文件路径。
 */
const CANONICAL_SIX = [
  {
    moduleId: "job_management",
    label: "作业管理",
    taskProgressId: "job_management",
    shortLabel: "作业管理",
    subtasks: [
      "作业待启动",
      "资料已上传",
      "规划设计排期已确认",
      "工程安装排期已确认",
      "集群联调排期已确认",
      "作业闭环完成",
    ],
  },
  {
    moduleId: "smart_survey_workbench",
    label: "智慧工勘",
    taskProgressId: "smart_survey",
    shortLabel: "智慧工勘",
    subtasks: ["场景筛选与底表过滤", "勘测数据汇总", "报告生成", "审批与分发闭环"],
  },
  {
    moduleId: "jmfz",
    label: "建模仿真",
    taskProgressId: "jmfz",
    shortLabel: "建模仿真",
    subtasks: ["BOQ 提取", "设备确认", "创建设备", "拓扑确认", "拓扑连接"],
  },
  {
    moduleId: "system_design",
    label: "系统设计",
    taskProgressId: "system_design",
    shortLabel: "系统设计",
    subtasks: ["需求与范围基线", "方案与架构评审", "设计基线冻结", "变更与风险登记"],
  },
  {
    moduleId: "device_install",
    label: "设备安装",
    taskProgressId: "device_install",
    shortLabel: "设备安装",
    subtasks: ["进场与验货", "安装与上电", "单机自检", "系统联线", "安规与资产标签"],
  },
  {
    moduleId: "sw_deploy_commission",
    label: "软件部署与调测",
    taskProgressId: "sw_deploy_commission",
    shortLabel: "软件部署与调测",
    subtasks: ["环境基线", "应用与中间件部署", "联调对点", "性能与稳定验证", "移交与培训"],
  },
];

function pickSubtasksFromApi(api, c) {
  const raw = api && api.taskProgress && Array.isArray(api.taskProgress.tasks) ? api.taskProgress.tasks : null;
  if (raw && raw.length) {
    return raw.map((t) => (typeof t === "string" ? t : String(t)));
  }
  return c.subtasks;
}

function mergeOne(api, c) {
  const subtasks = pickSubtasksFromApi(api, c);
  const taskProgressId = c.taskProgressId;
  const moduleName =
    (api && api.taskProgress && String(api.taskProgress.moduleName || "").trim()) || c.shortLabel;
  if (api && typeof api === "object") {
    return {
      ...api,
      label: c.label,
      showWorkbenchModuleStepper: true,
      taskProgress: {
        moduleId: taskProgressId,
        moduleName: moduleName || c.label,
        tasks: subtasks,
      },
    };
  }
  return {
    moduleId: c.moduleId,
    label: c.label,
    description: "模块未安装时仍可跟踪本阶段子任务与总体进度。",
    placeholder: true,
    showWorkbenchModuleStepper: true,
    taskProgress: {
      moduleId: taskProgressId,
      moduleName: c.shortLabel,
      tasks: c.subtasks,
    },
    dashboard: { docId: "", dataFile: "" },
  };
}

export function composeProjectRegistryItems(registryItems) {
  const fromApi = Array.isArray(registryItems) ? registryItems : [];
  const byId = new Map(
    fromApi
      .filter((x) => x && typeof x === "object" && typeof x.moduleId === "string" && x.moduleId.trim())
      .map((x) => [String(x.moduleId).trim(), x]),
  );
  return CANONICAL_SIX.map((c) => mergeOne(byId.get(c.moduleId), c));
}
