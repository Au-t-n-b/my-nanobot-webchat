"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import { loginLocalUser } from "@/lib/localAuth";
import {
  getOrInitDefaultProject,
  grantWorkspaceAccess,
  writeGlobalProjectContext,
} from "@/lib/globalProjectContext";

function userIdFromUsername(username: string): string {
  const u = username.trim();
  return `u_${u.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "user"}`;
}

export function PdOnboardingPrototype() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canGoHome = useMemo(() => true, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const u = username.trim();
    if (!u) {
      setError("请输入用户名后再登录。");
      return;
    }
    setBusy(true);
    try {
      const r = loginLocalUser(u, password);
      if (!r.ok) {
        setError(r.error);
        return;
      }

      setSuccess("登录成功，正在进入工作台...");

      const project = getOrInitDefaultProject();
      writeGlobalProjectContext({
        user: { id: userIdFromUsername(u), username: u, role: "member" },
        project,
        stage: "init",
      });
      grantWorkspaceAccess();

      // keep behavior identical to spec
      window.location.replace("/");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-dvh overflow-hidden" style={{ background: "var(--surface-0)", color: "var(--text-primary)" }}>
      <div
        className="pointer-events-none absolute -left-24 top-1/4 h-72 w-72 rounded-full opacity-40 blur-3xl"
        style={{ background: "color-mix(in oklab, var(--accent) 35%, transparent)" }}
      />
      <div
        className="pointer-events-none absolute -right-20 bottom-1/4 h-64 w-64 rounded-full opacity-30 blur-3xl"
        style={{ background: "color-mix(in oklab, var(--sdui-accent-blue) 40%, transparent)" }}
      />

      <header className="relative z-10 mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-4">
        <span className="text-sm font-semibold ui-text-primary">交付 claw 工作台</span>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          {canGoHome ? (
            <Link href="/" className="text-xs ui-text-muted hover:ui-text-primary">
              返回主界面
            </Link>
          ) : (
            <span className="text-xs ui-text-muted">返回主界面</span>
          )}
        </div>
      </header>

      <main className="relative z-10 mx-auto mt-10 w-full max-w-md px-4 pb-10">
        <div
          className="ui-panel rounded-2xl p-8 shadow-[var(--shadow-panel)] transition-transform duration-200 hover:-translate-y-0.5"
          style={{ backdropFilter: "blur(12px)" }}
        >
          <h1 className="text-lg font-semibold ui-text-primary">登录</h1>

          <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium ui-text-secondary">用户名</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="工号或账号"
                className="ui-input ui-input-focusable w-full rounded-xl px-4 py-3 text-sm"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium ui-text-secondary">密码</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                className="ui-input ui-input-focusable w-full rounded-xl px-4 py-3 text-sm"
              />
            </div>
            {error ? (
              <p className="text-xs" style={{ color: "var(--danger)" }}>
                {error}
              </p>
            ) : null}
            {success ? (
              <p className="text-xs" style={{ color: "var(--success)" }}>
                {success}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="ui-btn-accent ui-btn-sheen relative overflow-hidden rounded-xl py-3 text-sm font-medium transition-transform hover:scale-[1.02] active:scale-[0.99] disabled:opacity-50"
            >
              {busy ? "登录中…" : "登录"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

