"use client";

/**
 * Local demo projects: stored in localStorage only.
 * Intended for UI scoping (current project), not a server-side boundary.
 */

export type LocalProject = {
  id: string;
  name: string;
  /** 项目编码 */
  code?: string;
  /** 投标编码 */
  bidCode?: string;
  /** 场景 */
  scenario?: string;
  /** 规模 */
  scale?: string;
  /** 交付特点 */
  deliveryFeatures?: string;
  /** 语言 */
  language?: string;
  /** 项目群 */
  projectGroup?: string;
  /** 相关人（逗号分隔/自由文本） */
  stakeholders?: string;
  createdAt: number;
};

const PROJECTS_KEY = "nanobot_local_projects_v1";
const SELECTED_KEY = "nanobot_selected_project_v1";

function safeParseJson(raw: string | null): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

function normalizeProjects(value: unknown): LocalProject[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((x) => {
      const obj: Record<string, unknown> =
        x && typeof x === "object" ? (x as Record<string, unknown>) : {};
      return {
        id: typeof obj.id === "string" ? obj.id : "",
        name: typeof obj.name === "string" ? obj.name.trim() : "",
        code: typeof obj.code === "string" ? obj.code.trim() : "",
        bidCode: typeof obj.bidCode === "string" ? obj.bidCode.trim() : "",
        scenario: typeof obj.scenario === "string" ? obj.scenario.trim() : "",
        scale: typeof obj.scale === "string" ? obj.scale.trim() : "",
        deliveryFeatures: typeof obj.deliveryFeatures === "string" ? obj.deliveryFeatures.trim() : "",
        language: typeof obj.language === "string" ? obj.language.trim() : "",
        projectGroup: typeof obj.projectGroup === "string" ? obj.projectGroup.trim() : "",
        stakeholders: typeof obj.stakeholders === "string" ? obj.stakeholders.trim() : "",
        createdAt: typeof obj.createdAt === "number" ? obj.createdAt : Date.now(),
      } satisfies LocalProject;
    })
    .filter((p) => p.id && p.name);
}

function uuid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `proj_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }
}

export function listLocalProjects(): LocalProject[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(PROJECTS_KEY);
  return normalizeProjects(safeParseJson(raw));
}

export function getSelectedLocalProjectId(): string | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SELECTED_KEY);
  const v = raw ? raw.trim() : "";
  return v || null;
}

export function setSelectedLocalProjectId(projectId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SELECTED_KEY, projectId);
}

export function createLocalProject(name: string): LocalProject {
  if (typeof window === "undefined") {
    return { id: "server", name: name.trim() || "默认项目", createdAt: Date.now() };
  }
  const now = Date.now();
  const trimmed = name.trim();
  const project: LocalProject = { id: uuid(), name: trimmed || "默认项目", createdAt: now };
  const projects = listLocalProjects();
  const next = [project, ...projects];
  window.localStorage.setItem(PROJECTS_KEY, JSON.stringify(next));
  setSelectedLocalProjectId(project.id);
  return project;
}

export function createLocalProjectWithMeta(meta: Omit<LocalProject, "id" | "createdAt">): LocalProject {
  if (typeof window === "undefined") {
    return { id: "server", name: meta.name.trim() || "默认项目", createdAt: Date.now(), ...meta };
  }
  const now = Date.now();
  const project: LocalProject = {
    id: uuid(),
    name: meta.name.trim() || "默认项目",
    code: meta.code?.trim() || "",
    bidCode: meta.bidCode?.trim() || "",
    scenario: meta.scenario?.trim() || "",
    scale: meta.scale?.trim() || "",
    deliveryFeatures: meta.deliveryFeatures?.trim() || "",
    language: meta.language?.trim() || "",
    projectGroup: meta.projectGroup?.trim() || "",
    stakeholders: meta.stakeholders?.trim() || "",
    createdAt: now,
  };
  const projects = listLocalProjects();
  const next = [project, ...projects];
  window.localStorage.setItem(PROJECTS_KEY, JSON.stringify(next));
  setSelectedLocalProjectId(project.id);
  return project;
}

export function ensureAtLeastOneLocalProject(): { projects: LocalProject[]; selectedId: string } {
  if (typeof window === "undefined") return { projects: [], selectedId: "" };
  let projects = listLocalProjects();
  let selectedId = getSelectedLocalProjectId() ?? "";

  if (projects.length === 0) {
    const p = createLocalProject("默认项目");
    projects = [p];
    selectedId = p.id;
    return { projects, selectedId };
  }
  if (!selectedId || !projects.some((p) => p.id === selectedId)) {
    selectedId = projects[0]!.id;
    setSelectedLocalProjectId(selectedId);
  }
  return { projects, selectedId };
}

