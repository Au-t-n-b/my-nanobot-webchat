/**
 * 与 ``projectOverviewRegistry`` 中 CANONICAL_SIX 一致：常见 task_progress ``moduleId`` /
 * 技能目录 id → 模块 Tab / 卡片展示用中文名。
 */
export const MODULE_TAB_LABEL_BY_ID: Record<string, string> = {
  job_management: "作业管理",
  smart_survey: "智慧工勘",
  smart_survey_workbench: "智慧工勘",
  jmfz: "建模仿真",
  modeling_simulation_workbench: "建模仿真",
  system_design: "系统设计",
  device_install: "设备安装",
  sw_deploy_commission: "软件部署与调测",
};

/**
 * 建模仿真阶段：task_progress / skills 目录历史上混用 ``jmfz`` 与 ``modeling_simulation_workbench``，
 * 侧栏与 Tab 的 Map 键统一为 ``jmfz``（与 ``projectOverviewRegistry`` 的 moduleId 一致），避免重复 Tab。
 */
export function canonicalModuleIdForMerge(moduleId: string): string {
  const raw = String(moduleId ?? "").trim();
  if (!raw) return raw;
  const lower = raw.toLowerCase();
  if (lower === "modeling_simulation_workbench" || lower === "jmfz") {
    return "jmfz";
  }
  return raw;
}

/** Patch 到达前占位 Tab：已知 id 用中文，其余保持可读英文 Title Case */
export function moduleTabLabelFromId(moduleId: string): string {
  const id = String(moduleId ?? "").trim();
  if (MODULE_TAB_LABEL_BY_ID[id]) return MODULE_TAB_LABEL_BY_ID[id];
  const lower = id.toLowerCase();
  if (MODULE_TAB_LABEL_BY_ID[lower]) return MODULE_TAB_LABEL_BY_ID[lower];
  return id.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
