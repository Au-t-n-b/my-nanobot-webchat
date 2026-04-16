"use client";

import { ensureAtLeastOneLocalProject, listLocalProjects, type LocalProject } from "@/lib/localProjects";

export type GlobalUser = {
  id: string;
  username: string;
  role?: string;
  nickname?: string;
};

export type GlobalProject = LocalProject;

export type GlobalProjectContext = {
  user: GlobalUser;
  project: GlobalProject;
  stage: string;
  updatedAt: number;
};

const CTX_KEY = "nanobot_global_project_context_v1";
const ACCESS_KEY = "nanobot_workspace_access_v1";

function safeJsonParse(raw: string | null): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

function normalizeContext(value: unknown): GlobalProjectContext | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  const user = v.user;
  const project = v.project;
  const stage = typeof v.stage === "string" ? v.stage : "";
  if (!user || typeof user !== "object") return null;
  if (!project || typeof project !== "object") return null;
  const u = user as Record<string, unknown>;
  const p = project as Record<string, unknown>;
  const username = typeof u.username === "string" ? u.username.trim() : "";
  const userId = typeof u.id === "string" ? u.id.trim() : "";
  const projectId = typeof p.id === "string" ? p.id.trim() : "";
  const projectName = typeof p.name === "string" ? p.name.trim() : "";
  if (!username || !userId || !projectId || !projectName) return null;
  return {
    user: {
      id: userId,
      username,
      role: typeof u.role === "string" ? u.role.trim() : "",
      nickname: typeof u.nickname === "string" ? u.nickname.trim() : "",
    },
    project: {
      id: projectId,
      name: projectName,
      code: typeof p.code === "string" ? p.code.trim() : "",
      bidCode: typeof p.bidCode === "string" ? p.bidCode.trim() : "",
      scenario: typeof p.scenario === "string" ? p.scenario.trim() : "",
      scale: typeof p.scale === "string" ? p.scale.trim() : "",
      deliveryFeatures: typeof p.deliveryFeatures === "string" ? p.deliveryFeatures.trim() : "",
      language: typeof p.language === "string" ? p.language.trim() : "",
      projectGroup: typeof p.projectGroup === "string" ? p.projectGroup.trim() : "",
      stakeholders: typeof p.stakeholders === "string" ? p.stakeholders.trim() : "",
      createdAt: typeof p.createdAt === "number" ? p.createdAt : Date.now(),
    },
    stage: stage || "init",
    updatedAt: typeof v.updatedAt === "number" ? v.updatedAt : Date.now(),
  };
}

export function readGlobalProjectContext(): GlobalProjectContext | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(CTX_KEY);
  return normalizeContext(safeJsonParse(raw));
}

export function writeGlobalProjectContext(next: Omit<GlobalProjectContext, "updatedAt">): void {
  if (typeof window === "undefined") return;
  const payload: GlobalProjectContext = { ...next, updatedAt: Date.now() };
  window.localStorage.setItem(CTX_KEY, JSON.stringify(payload));
}

export function patchGlobalProjectContext(patch: Partial<Pick<GlobalProjectContext, "user" | "project" | "stage">>): void {
  if (typeof window === "undefined") return;
  const cur = readGlobalProjectContext();
  if (!cur) return;
  const merged: GlobalProjectContext = {
    ...cur,
    user: patch.user ? { ...cur.user, ...patch.user } : cur.user,
    project: patch.project ? { ...cur.project, ...patch.project } : cur.project,
    stage: typeof patch.stage === "string" && patch.stage.trim() ? patch.stage.trim() : cur.stage,
    updatedAt: Date.now(),
  };
  window.localStorage.setItem(CTX_KEY, JSON.stringify(merged));
}

export function clearGlobalProjectContext(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(CTX_KEY);
  window.localStorage.removeItem(ACCESS_KEY);
}

export function grantWorkspaceAccess(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, "1");
}

export function hasWorkspaceAccess(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(ACCESS_KEY) === "1";
}

export function getOrInitDefaultProject(): LocalProject {
  const { projects, selectedId } = ensureAtLeastOneLocalProject();
  const p = projects.find((x) => x.id === selectedId) ?? projects[0];
  if (p) return p;
  // fallback: if storage is corrupted but listLocalProjects is empty
  const list = listLocalProjects();
  return list[0] ?? { id: "default", name: "默认项目", createdAt: Date.now() };
}

