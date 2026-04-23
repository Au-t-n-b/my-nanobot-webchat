export function composeProjectRegistryItems(registryItems) {
  /**
   * Skill-First UI（2026-04）：项目总览作为“全局进度容器”仍需要稳定展示交付阶段。
   * 这里返回一个**固定的 6 阶段模块序列**，并与后端/本地扫描到的 modules 合并：
   * - 若 registryItems 中存在该 moduleId：使用其 label/description/taskProgress/dashboard 配置
   * - 若不存在：生成 placeholder 项（用于 Stepper/总览展示），后续模块目录与 module.json 就位后自动替换
   */

  const ordered = [
    { moduleId: "job_management", label: "作业管理" },
    { moduleId: "zhgk", label: "智慧工勘" },
    { moduleId: "modeling_simulation_workbench", label: "建模仿真" },
    { moduleId: "system_design", label: "系统设计" },
    { moduleId: "device_install", label: "设备安装" },
    { moduleId: "sw_deploy_commission", label: "软件部署与调测" },
  ];

  const byId = new Map(
    Array.isArray(registryItems)
      ? registryItems
          .filter((x) => x && typeof x === "object" && typeof x.moduleId === "string" && x.moduleId.trim())
          .map((x) => [x.moduleId.trim(), x])
      : [],
  );

  return ordered.map(({ moduleId, label }) => {
    const existing = byId.get(moduleId);
    if (existing) return existing;
    return {
      moduleId,
      label,
      description: "",
      placeholder: true,
      taskProgress: {
        moduleId,
        moduleName: label,
        tasks: [],
      },
      dashboard: {
        docId: "",
        dataFile: `skills/${moduleId}/data/dashboard.json`,
      },
    };
  });
}
