"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { hasWorkspaceAccess, readGlobalProjectContext } from "@/lib/globalProjectContext";
import { prefetchWorkbenchShell } from "@/lib/workbenchShellPrefetch";

/**
 * 已写入工作区上下文且具备访问令牌时，从落地页自动进入 /workbench（与登录提交后的跳转同契约）。
 */
export function useRedirectToWorkbenchWhenAuthed(): void {
  const router = useRouter();

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!hasWorkspaceAccess() || !readGlobalProjectContext()) return;
    prefetchWorkbenchShell(router);
    router.replace("/workbench");
    const t = window.setTimeout(() => {
      const p = window.location.pathname.replace(/\/$/, "") || "/";
      if (p === "/" || p === "") window.location.replace("/workbench");
    }, 250);
    return () => window.clearTimeout(t);
  }, [router]);
}
