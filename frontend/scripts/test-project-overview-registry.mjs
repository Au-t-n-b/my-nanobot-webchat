import test from "node:test";
import assert from "node:assert/strict";

import { composeProjectRegistryItems } from "../lib/projectOverviewRegistry.js";

test("composeProjectRegistryItems only returns installed modules in preferred order", () => {
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
    {
      moduleId: "job_management",
      label: "作业管理",
      description: "jm",
      taskProgress: { moduleId: "job_management", moduleName: "作业管理", tasks: [] },
      dashboard: { docId: "dashboard:job-management", dataFile: "skills/job_management/data/dashboard.json" },
    },
  ]);

  assert.deepEqual(
    items.map((item) => item.moduleId),
    ["job_management", "smart_survey_workbench", "intelligent_analysis_workbench"],
  );
  assert.equal(items[1].dashboard.dataFile, "skills/smart_survey_workbench/data/dashboard.json");
  assert.ok(!items.some((x) => x.placeholder));
});

test("composeProjectRegistryItems empty input yields empty list", () => {
  assert.deepEqual(composeProjectRegistryItems([]), []);
  assert.deepEqual(composeProjectRegistryItems(null), []);
});
