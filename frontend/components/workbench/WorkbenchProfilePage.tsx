"use client";

import { useMemo } from "react";
import { ArrowLeft, Settings2, UserRound, Users } from "lucide-react";
import { AdminMembersPanel } from "@/components/workbench/AdminMembersPanel";
import { useAuthState } from "@/lib/authStore";

export type ProfileSubView = "main" | "settings" | "members";

type Props = {
  subView: ProfileSubView;
  onSubViewChange: (v: ProfileSubView) => void;
  onBack: () => void;
};

function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition " +
        (active
          ? "border-[color-mix(in_oklab,var(--accent)_45%,var(--border-subtle))] bg-[var(--surface-2)] ui-text-primary"
          : "border-[var(--border-subtle)] bg-[var(--surface-1)] ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary")
      }
    >
      {icon}
      {label}
    </button>
  );
}

export function WorkbenchProfilePage({ subView, onSubViewChange, onBack }: Props) {
  const { user } = useAuthState();
  const canManageMembers = user?.accountRole === "admin" || user?.accountRole === "pd";
  const label = useMemo(() => user?.realName?.trim() || user?.workId?.trim() || "未登录", [user]);

  if (subView === "members") {
    return <AdminMembersPanel onBack={() => onSubViewChange("main")} />;
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2.5 sm:px-4">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary"
        >
          <ArrowLeft size={16} aria-hidden />
          返回工作台
        </button>
        <div className="min-w-0 flex-1" />
        <div className="inline-flex items-center gap-2">
          <TabButton active={subView === "main"} icon={<UserRound size={16} aria-hidden />} label="个人中心" onClick={() => onSubViewChange("main")} />
          <TabButton active={subView === "settings"} icon={<Settings2 size={16} aria-hidden />} label="设置" onClick={() => onSubViewChange("settings")} />
          {canManageMembers ? (
            <TabButton active={false} icon={<Users size={16} aria-hidden />} label="成员管理" onClick={() => onSubViewChange("members")} />
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {subView === "main" ? (
          <div className="max-w-3xl space-y-4">
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
            </div>
          </div>
        ) : (
          <div className="max-w-3xl space-y-4">
            <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5 shadow-[var(--shadow-card)]">
              <div className="text-sm font-semibold ui-text-primary">设置</div>
              <p className="mt-2 text-sm ui-text-secondary">MVP 阶段先保留占位。</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

