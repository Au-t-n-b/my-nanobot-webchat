"use client";

import { LogOut, UserRound } from "lucide-react";
import { useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { clearAuthSession, useAuthState } from "@/lib/authStore";
import { clearGlobalProjectContext } from "@/lib/globalProjectContext";

export function ProfilePane({ onAfterLogout }: { onAfterLogout?: () => void }) {
  const router = useRouter();
  const { user } = useAuthState();
  const label = useMemo(() => user?.realName?.trim() || user?.workId?.trim() || "未登录", [user]);

  const logout = useCallback(() => {
    clearAuthSession();
    clearGlobalProjectContext();
    onAfterLogout?.();
    router.replace("/");
  }, [onAfterLogout, router]);

  return (
    <div className="p-4">
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5 shadow-[var(--shadow-card)]">
        <div className="flex items-start gap-3">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)]">
            <UserRound size={18} aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold ui-text-primary">当前账号</div>
            <div className="mt-1 text-sm ui-text-secondary">{label}</div>
            <div className="mt-2 text-xs ui-text-muted">
              {user?.accountRole ? `权限：${user.accountRole}` : "未获取到 accountRole（可能是旧登录态）"}
            </div>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={logout}
            className="inline-flex items-center gap-2 rounded-xl border border-[color-mix(in_oklab,var(--danger)_45%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--danger)_12%,var(--surface-1))] px-3 py-2 text-sm ui-text-primary hover:opacity-90"
          >
            <LogOut size={16} aria-hidden />
            退出登录
          </button>
        </div>
      </div>
    </div>
  );
}

