"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, LogOut, Settings2, UserRound, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { clearGlobalProjectContext } from "@/lib/globalProjectContext";
import { clearAuthSession, hydrateAuthFromStorage, useAuthState } from "@/lib/authStore";

export type PersonalInfoMenuAction = "profile_home" | "settings" | "member_management" | "logout";

type Props = {
  variant?: "nav" | "full";
  className?: string;
  onMenuAction?: (action: PersonalInfoMenuAction) => void;
};

function useClickOutside(ref: React.RefObject<HTMLElement>, onOutside: () => void) {
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const el = ref.current;
      if (!el) return;
      if (e.target instanceof Node && el.contains(e.target)) return;
      onOutside();
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [onOutside, ref]);
}

export function SidebarPersonalInfo({ variant = "nav", className = "", onMenuAction }: Props) {
  const router = useRouter();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const { user } = useAuthState();

  useEffect(() => {
    hydrateAuthFromStorage();
  }, []);

  useClickOutside(
    wrapRef,
    useCallback(() => setOpen(false), []),
  );

  const canManageMembers = user?.accountRole === "admin" || user?.accountRole === "pd";
  const label = useMemo(() => {
    const name = user?.realName?.trim();
    const wid = user?.workId?.trim();
    return name || wid || "账号与资料";
  }, [user]);

  const logout = useCallback(() => {
    setOpen(false);
    clearAuthSession();
    clearGlobalProjectContext();
    router.replace("/");
  }, [router]);

  const run = useCallback(
    (action: PersonalInfoMenuAction) => {
      setOpen(false);
      if (action === "logout") return logout();
      onMenuAction?.(action);
    },
    [logout, onMenuAction],
  );

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <button
        type="button"
        className={
          "inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border-subtle)] " +
          "bg-[var(--surface-1)] px-3 py-2 text-sm ui-text-secondary transition-colors hover:bg-[var(--surface-3)] hover:ui-text-primary " +
          (variant === "nav" ? "h-9 px-2.5 py-1.5" : "")
        }
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={label}
      >
        <UserRound size={16} aria-hidden />
        {variant === "full" ? <span className="min-w-0 truncate">{label}</span> : null}
        <ChevronDown size={14} aria-hidden className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open ? (
        <div
          className="absolute right-0 top-full z-[120] mt-2 w-56 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-1.5 shadow-[var(--shadow-float)]"
          role="menu"
        >
          <button type="button" className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--surface-3)]" onClick={() => run("profile_home")}>
            <span className="inline-flex items-center gap-2">
              <UserRound size={16} aria-hidden />
              个人中心
            </span>
          </button>
          <button type="button" className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--surface-3)]" onClick={() => run("settings")}>
            <span className="inline-flex items-center gap-2">
              <Settings2 size={16} aria-hidden />
              设置
            </span>
          </button>
          {canManageMembers ? (
            <button
              type="button"
              className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-[var(--surface-3)]"
              onClick={() => run("member_management")}
            >
              <span className="inline-flex items-center gap-2">
                <Users size={16} aria-hidden />
                成员管理
              </span>
            </button>
          ) : null}
          <div className="my-1.5 h-px bg-[var(--border-subtle)]" />
          <button
            type="button"
            className="w-full rounded-lg px-3 py-2 text-left text-sm text-red-400 hover:bg-red-500/10"
            onClick={() => run("logout")}
          >
            <span className="inline-flex items-center gap-2">
              <LogOut size={16} aria-hidden />
              退出登录
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}

