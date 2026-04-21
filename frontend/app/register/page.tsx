"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeToggle";
import { isLoggedIn, registerLocalUser } from "@/lib/localAuth";

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isLoggedIn()) router.replace("/workbench");
  }, [router]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = registerLocalUser(username, password, password2);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      router.replace("/workbench");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-dvh overflow-hidden px-4 py-8" style={{ background: "var(--surface-0)", color: "var(--text-primary)" }}>
      <div
        className="pointer-events-none absolute -left-24 top-1/4 h-72 w-72 rounded-full opacity-40 blur-3xl"
        style={{ background: "color-mix(in oklab, var(--accent) 35%, transparent)" }}
      />
      <div
        className="pointer-events-none absolute -right-20 bottom-1/4 h-64 w-64 rounded-full opacity-30 blur-3xl"
        style={{ background: "color-mix(in oklab, var(--sdui-accent-blue) 40%, transparent)" }}
      />

      <header className="relative z-10 mx-auto flex max-w-lg items-center justify-between gap-3">
        <span className="text-sm font-semibold ui-text-primary">交付 claw 工作台</span>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/login" className="text-xs ui-text-muted hover:ui-text-primary">
            登录
          </Link>
        </div>
      </header>

      <main className="relative z-10 mx-auto mt-10 w-full max-w-md">
        <div
          className="ui-panel rounded-2xl p-8 shadow-[var(--shadow-panel)] transition-transform duration-200 hover:-translate-y-0.5"
          style={{ backdropFilter: "blur(12px)" }}
        >
          <h1 className="text-lg font-semibold ui-text-primary">注册</h1>
          <p className="mt-1 text-xs ui-text-muted">创建本地演示账号后自动登录。</p>

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
                autoComplete="new-password"
                placeholder="至少 4 位"
                className="ui-input ui-input-focusable w-full rounded-xl px-4 py-3 text-sm"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium ui-text-secondary">确认密码</label>
              <input
                type="password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                autoComplete="new-password"
                placeholder="再次输入密码"
                className="ui-input ui-input-focusable w-full rounded-xl px-4 py-3 text-sm"
              />
            </div>
            {error ? (
              <p className="text-xs" style={{ color: "var(--danger)" }}>
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="ui-btn-accent relative overflow-hidden rounded-xl py-3 text-sm font-medium transition-transform hover:scale-[1.02] active:scale-[0.99] disabled:opacity-50"
            >
              {busy ? "提交中…" : "注册并进入"}
            </button>
          </form>

          <p className="mt-4 text-center text-xs ui-text-muted">
            已有账号？{" "}
            <Link href="/login" className="font-medium text-[var(--accent)] hover:underline">
              登录
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
