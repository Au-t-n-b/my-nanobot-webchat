const CANONICAL_STAGE_MODULES = [
  {
    moduleId: "job_management",
    label: "作业管理",
    description: "负责项目开工前的作业编排、资源准备与前置检查。",
    aliases: ["作业管理"],
  },
  {
    moduleId: "zhgk_module_case",
    label: "智慧工勘",
    description: "负责工勘场景选择、资料上传与工勘报告联动分析。",
    aliases: ["智慧工勘", "智慧工勘模块案例"],
  },
  {
    moduleId: "modeling_simulation",
    label: "建模仿真",
    description: "负责建模、仿真推演与结果校核。",
    aliases: ["建模仿真"],
  },
  {
    moduleId: "intelligent_analysis_workbench",
    label: "智能分析工作台",
    description: "负责跨模块分析编排、HITL 交互与结论汇总。",
    aliases: ["智能分析工作台"],
  },
];

function defaultRegistryItem(stage) {
  return {
    moduleId: stage.moduleId,
    label: stage.label,
    description: stage.description,
    placeholder: true,
    taskProgress: {
      moduleId: stage.moduleId,
      moduleName: stage.label,
      tasks: [],
    },
    dashboard: {
      docId: "",
      dataFile: "",
    },
  };
}

function findExisting(items, stage) {
  const loweredAliases = new Set(stage.aliases.map((item) => item.toLowerCase()));
  return items.find((item) => {
    const moduleId = String(item.moduleId || "").trim().toLowerCase();
    const label = String(item.label || "").trim().toLowerCase();
    return moduleId === stage.moduleId.toLowerCase() || loweredAliases.has(label);
  });
}

function mergeStage(stage, existing) {
  if (!existing) return defaultRegistryItem(stage);
  return {
    ...existing,
    label: stage.label,
    description: String(existing.description || "").trim() || stage.description,
    placeholder: false,
    taskProgress: {
      moduleId: String(existing.taskProgress?.moduleId || existing.moduleId || stage.moduleId).trim() || stage.moduleId,
      moduleName: String(existing.taskProgress?.moduleName || stage.label).trim() || stage.label,
      tasks: Array.isArray(existing.taskProgress?.tasks) ? existing.taskProgress.tasks : [],
    },
    dashboard: {
      docId: String(existing.dashboard?.docId || "").trim(),
      dataFile: String(existing.dashboard?.dataFile || "").trim(),
    },
  };
}

export function composeProjectRegistryItems(registryItems) {
  const source = Array.isArray(registryItems) ? registryItems : [];
  const usedModuleIds = new Set();
  const canonical = CANONICAL_STAGE_MODULES.map((stage) => {
    const existing = findExisting(source, stage);
    if (existing?.moduleId) usedModuleIds.add(existing.moduleId);
    return mergeStage(stage, existing);
  });

  const remaining = source
    .filter((item) => !usedModuleIds.has(item.moduleId))
    .map((item) => ({
      ...item,
      placeholder: Boolean(item.placeholder),
    }));

  return [...canonical, ...remaining];
}
