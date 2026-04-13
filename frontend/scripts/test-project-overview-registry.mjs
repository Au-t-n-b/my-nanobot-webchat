import test from "node:test";
import assert from "node:assert/strict";

import { composeProjectRegistryItems } from "../lib/projectOverviewRegistry.js";

test("composeProjectRegistryItems prepends canonical modules and preserves real smart survey/workbench entries", () => {
  const items = composeProjectRegistryItems([
    {
      moduleId: "intelligent_analysis_workbench",
      label: "智能分析工作台",
      description: "真实工作台",
      taskProgress: { moduleId: "intelligent_analysis_workbench", moduleName: "智能分析工作台", tasks: [] },
      dashboard: { docId: "dashboard:workbench", dataFile: "skills/intelligent_analysis_workbench/data/dashboard.json" },
    },
    {
      moduleId: "smart_survey_workbench",
      label: "智慧工勘模块",
      description: "真实智慧工勘模块",
      taskProgress: { moduleId: "smart_survey_workbench", moduleName: "智慧工勘", tasks: [] },
      dashboard: { docId: "dashboard:smart-survey", dataFile: "skills/smart_survey_workbench/data/dashboard.json" },
    },
  ]);

  assert.deepEqual(
    items.slice(0, 4).map((item) => [item.moduleId, item.label, Boolean(item.placeholder)]),
    [
      ["job_management", "作业管理", true],
      ["smart_survey_workbench", "智慧工勘", false],
      ["modeling_simulation_workbench", "建模仿真模块", true],
      ["intelligent_analysis_workbench", "智能分析工作台", false],
    ],
  );
  assert.equal(items[1].dashboard.dataFile, "skills/smart_survey_workbench/data/dashboard.json");
  assert.match(items[1].description, /工勘|报告/);
  assert.match(items[2].description, /访问页|嵌入网页/);
  assert.doesNotMatch(items[2].description, /哔哩哔哩/);
});
