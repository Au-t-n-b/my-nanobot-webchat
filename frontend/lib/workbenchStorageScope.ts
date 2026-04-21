"use client";

import { getSelectedLocalProjectId } from "@/lib/localProjects";
import { readGlobalProjectContext } from "@/lib/globalProjectContext";
import { chatStorageScopeFromParts } from "@/lib/workbenchStorageKeys";

export function getAccountStorageId(): string {
  if (typeof window === "undefined") return "_ssr";
  const ctx = readGlobalProjectContext();
  const id = ctx?.user?.id?.trim();
  if (id) return id.slice(0, 80);
  return "_guest";
}

export function getWorkbenchChatStorageScope(): string {
  if (typeof window === "undefined") return chatStorageScopeFromParts("_ssr", "");
  const account = getAccountStorageId();
  let project = "";
  try {
    project = getSelectedLocalProjectId()?.trim() ?? "";
  } catch {
    project = "";
  }
  return chatStorageScopeFromParts(account, project);
}
