import test from "node:test";
import assert from "node:assert/strict";

import { composeProjectRegistryItems } from "../lib/projectOverviewRegistry.js";

test("composeProjectRegistryItems prepends canonical modules and preserves real zhgk/workbench entries", () => {
  const items = composeProjectRegistryItems([
    {
      moduleId: "intelligent_analysis_workbench",
      label: "智能分析工作台",
      description: "真实工作台",
      taskProgress: { moduleId: "intelligent_analysis_workbench", moduleName: "智能分析工作台", tasks: [] },
      dashboard: { docId: "dashboard:workbench", dataFile: "skills/intelligent_analysis_workbench/data/dashboard.json" },
    },
    {
      moduleId: "zhgk_module_case",
      label: "智慧工勘模块案例",
      description: "真实工勘模块",
      taskProgress: { moduleId: "zhgk_module_case", moduleName: "智慧工勘", tasks: [] },
      dashboard: { docId: "dashboard:zhgk", dataFile: "skills/zhgk_module_case/data/dashboard.json" },
    },
  ]);

  assert.deepEqual(
    items.slice(0, 4).map((item) => [item.moduleId, item.label, Boolean(item.placeholder)]),
    [
      ["job_management", "作业管理", true],
      ["zhgk_module_case", "智慧工勘", false],
      ["modeling_simulation", "建模仿真", true],
      ["intelligent_analysis_workbench", "智能分析工作台", false],
    ],
  );
  assert.equal(items[1].dashboard.dataFile, "skills/zhgk_module_case/data/dashboard.json");
});
