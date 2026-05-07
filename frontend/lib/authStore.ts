"use client";

import { useSyncExternalStore } from "react";

export type AuthUser = {
  userId: string;
  workId: string;
  realName: string;
  roleCode?: string;
  accountRole?: "admin" | "pd" | "employee";
  role?: "pd" | "user";
};

type AuthState = {
  token: string | null;
  user: AuthUser | null;
};

const LS_KEY = "nanobot_auth_state_v1";

let state: AuthState = { token: null, user: null };
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function safeParse(raw: string | null): AuthState | null {
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as unknown;
    if (!j || typeof j !== "object") return null;
    const o = j as Record<string, unknown>;
    const token = typeof o.token === "string" && o.token.trim() ? o.token.trim() : null;
    const u = o.user;
    let user: AuthUser | null = null;
    if (u && typeof u === "object") {
      const uu = u as Record<string, unknown>;
      const userId = typeof uu.userId === "string" ? uu.userId : "";
      const workId = typeof uu.workId === "string" ? uu.workId : "";
      const realName = typeof uu.realName === "string" ? uu.realName : "";
      if (userId && workId) {
        user = {
          userId,
          workId,
          realName,
          roleCode: typeof uu.roleCode === "string" ? uu.roleCode : undefined,
          accountRole: (uu.accountRole as AuthUser["accountRole"]) ?? undefined,
          role: (uu.role as AuthUser["role"]) ?? undefined,
        };
      }
    }
    return { token, user };
  } catch {
    return null;
  }
}

function persist(next: AuthState) {
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
}

export function hydrateAuthFromStorage(): void {
  if (typeof window === "undefined") return;
  const next = safeParse(window.localStorage.getItem(LS_KEY));
  if (!next) return;
  state = next;
  emit();
}

export function getAuthToken(): string | null {
  return state.token;
}

export function getAuthUser(): AuthUser | null {
  return state.user;
}

export function isAuthed(): boolean {
  return Boolean(state.token && state.user?.userId && state.user?.workId);
}

export function setAuthSession(token: string, user: AuthUser): void {
  state = { token, user };
  if (typeof window !== "undefined") persist(state);
  emit();
}

export function clearAuthSession(): void {
  state = { token: null, user: null };
  try {
    window.localStorage.removeItem(LS_KEY);
  } catch {
    // ignore
  }
  emit();
}

export function useAuthState(): AuthState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
    () => state,
  );
}

