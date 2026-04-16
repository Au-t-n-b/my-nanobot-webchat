"use client";

import { useMemo } from "react";
import { useProjectOverviewStore } from "@/lib/projectOverviewStore";

export function useLegacyModuleActionAllowed(moduleId: string | undefined | null): {
  allowed: boolean;
  reason?: string;
} {
  const trimmed = String(moduleId ?? "").trim();
  const { registryLoaded, hasInRegistry } = useProjectOverviewStore((snapshot) => ({
    registryLoaded: snapshot.registryLoaded,
    hasInRegistry: snapshot.registryItems.some((item) => item.moduleId === trimmed),
  }));

  return useMemo(() => {
    if (!trimmed) return { allowed: false, reason: "缺少 moduleId" };
    if (!registryLoaded) return { allowed: false, reason: "legacy registry 尚未加载（/api/modules）" };
    if (!hasInRegistry) return { allowed: false, reason: "不在 legacy 白名单（平台 registry 未登记）" };
    return { allowed: true };
  }, [trimmed, registryLoaded, hasInRegistry]);
}

export function formatLegacyModuleActionBlockedMessage(moduleId: string | undefined | null, reason?: string): string {
  const mid = String(moduleId ?? "").trim() || "(unknown)";
  const r = reason?.trim() ? `，原因：${reason.trim()}` : "";
  return `已拦截 legacy module_action（Option 1 白名单隔离）：moduleId=${mid}${r}`;
}

