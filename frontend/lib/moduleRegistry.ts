import fs from "fs";
import os from "os";
import path from "path";

export type ProjectModuleRegistryItem = {
  moduleId: string;
  label: string;
  description: string;
  taskProgress: {
    moduleId: string;
    moduleName: string;
    tasks: string[];
  };
  dashboard: {
    docId: string;
    dataFile: string;
  };
};

type RawModuleContract = {
  moduleId?: unknown;
  docId?: unknown;
  dataFile?: unknown;
  description?: unknown;
  caseTemplate?: {
    moduleTitle?: unknown;
    moduleGoal?: unknown;
  } | null;
  taskProgress?: {
    moduleId?: unknown;
    moduleName?: unknown;
    tasks?: unknown;
  } | null;
};

function getSkillsRoot(): string {
  const override = process.env.NANOBOT_AGUI_SKILLS_ROOT?.trim();
  if (override) return path.resolve(override.replace(/^~/, os.homedir()));
  return path.join(os.homedir(), ".nanobot", "workspace", "skills");
}

function toTrimmedString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? "").trim()).filter(Boolean);
}

function normalizeModuleRegistryItem(raw: RawModuleContract): ProjectModuleRegistryItem | null {
  const moduleId = toTrimmedString(raw.moduleId);
  if (!moduleId) return null;

  const caseTemplate = raw.caseTemplate && typeof raw.caseTemplate === "object" ? raw.caseTemplate : null;
  const taskProgress = raw.taskProgress && typeof raw.taskProgress === "object" ? raw.taskProgress : null;

  const label =
    toTrimmedString(caseTemplate?.moduleTitle) ||
    toTrimmedString(taskProgress?.moduleName) ||
    moduleId;
  const description =
    toTrimmedString(caseTemplate?.moduleGoal) ||
    toTrimmedString(raw.description);

  return {
    moduleId,
    label,
    description,
    taskProgress: {
      moduleId: toTrimmedString(taskProgress?.moduleId) || moduleId,
      moduleName: toTrimmedString(taskProgress?.moduleName) || label,
      tasks: toStringList(taskProgress?.tasks),
    },
    dashboard: {
      docId: toTrimmedString(raw.docId),
      dataFile: toTrimmedString(raw.dataFile),
    },
  };
}

export function listLocalModules(): ProjectModuleRegistryItem[] {
  const skillsRoot = getSkillsRoot();
  let entries: fs.Dirent[] = [];
  try {
    entries = fs.readdirSync(skillsRoot, { withFileTypes: true });
  } catch {
    return [];
  }

  const items: ProjectModuleRegistryItem[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const moduleFile = path.join(skillsRoot, entry.name, "module.json");
    if (!fs.existsSync(moduleFile)) continue;

    try {
      const raw = JSON.parse(fs.readFileSync(moduleFile, "utf8")) as RawModuleContract;
      const item = normalizeModuleRegistryItem(raw);
      if (item) items.push(item);
    } catch {
      continue;
    }
  }

  items.sort((left, right) => left.moduleId.localeCompare(right.moduleId));
  return items;
}
