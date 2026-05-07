"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Terminal } from "lucide-react";
import {
  getOrInitDefaultProject,
  grantWorkspaceAccess,
  writeGlobalProjectContext,
} from "@/lib/globalProjectContext";
import { hydrateAuthFromStorage, setAuthSession } from "@/lib/authStore";
import { prefetchWorkbenchShell, schedulePrefetchWorkbenchShell } from "@/lib/workbenchShellPrefetch";
import { useRedirectToWorkbenchWhenAuthed } from "@/hooks/useRedirectToWorkbenchWhenAuthed";
import styles from "./landing.module.css";
import Link from "next/link";

export default function LandingClient() {
  const router = useRouter();
  const [loginOpen, setLoginOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  /** nanobot 全局上下文当前仅存 localStorage；勾选不改变存储分层，仅保留落地页 UI 一致性 */
  const [remember, setRemember] = useState(true);
  const [isEntering, setIsEntering] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useRedirectToWorkbenchWhenAuthed();

  useEffect(() => {
    hydrateAuthFromStorage();
  }, []);

  useEffect(() => {
    schedulePrefetchWorkbenchShell(router);
  }, [router]);

  useEffect(() => {
    if (!loginOpen) return;
    schedulePrefetchWorkbenchShell(router);
  }, [loginOpen, router]);

  useEffect(() => {
    if (!loginOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [loginOpen]);

  useEffect(() => {
    if (!loginOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isEntering) setLoginOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [loginOpen, isEntering]);

  const closeLogin = useCallback(() => {
    if (isEntering) return;
    setLoginOpen(false);
    setLoginError(null);
  }, [isEntering]);

  const openLogin = useCallback(() => {
    setLoginOpen(true);
    queueMicrotask(() => {
      prefetchWorkbenchShell(router);
    });
  }, [router]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isEntering) return;
    setLoginError(null);
    const u = username.trim();
    const pwd = password;
    if (!u) {
      setLoginError("请输入用户名。");
      return;
    }
    if (!pwd) {
      setLoginError("请输入密码。");
      return;
    }
    setIsEntering(true);
    void (async () => {
      try {
        const r = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workId: u, password: pwd }),
        });
        const j = (await r.json().catch(() => ({}))) as { token?: unknown; user?: unknown; detail?: unknown };
        if (!r.ok) {
          setLoginError(String(j.detail || `登录失败（HTTP ${r.status}）`));
          setIsEntering(false);
          return;
        }
        const token = typeof j.token === "string" ? j.token.trim() : "";
        const user =
          j.user && typeof j.user === "object"
            ? (j.user as Partial<{
                userId: string;
                workId: string;
                realName: string;
                roleCode: string;
                accountRole: "admin" | "pd" | "employee";
                role: "pd" | "user";
              }>)
            : null;
        if (!token || !user?.userId || !user?.workId) {
          setLoginError("登录响应缺少 token 或 user。");
          setIsEntering(false);
          return;
        }
        setAuthSession(token, {
          userId: String(user.userId),
          workId: String(user.workId),
          realName: String(user.realName || user.workId),
          roleCode: String(user.roleCode || ""),
          accountRole: user.accountRole,
          role: user.role,
        });
        const project = getOrInitDefaultProject();
        writeGlobalProjectContext({
          user: { id: String(user.userId), username: String(user.workId), role: "member", nickname: String(user.realName || "") },
          project,
          stage: "init",
        });
        grantWorkspaceAccess();
        prefetchWorkbenchShell(router);
        // 先关掉登录弹层，只保留全屏「正在进入…」直到离开落地页，避免 3s 后误回弹到登录窗
        setLoginOpen(false);
        setLoginError(null);
        router.replace("/workbench");
        window.setTimeout(() => {
          const p = window.location.pathname.replace(/\/$/, "") || "/";
          if (p !== "/workbench") {
            window.location.replace("/workbench");
            return;
          }
          // 客户端路由已落在 /workbench 时再卸加载态
          setIsEntering(false);
        }, 300);
      } catch (e) {
        setLoginError(e instanceof Error ? e.message : String(e));
        setIsEntering(false);
      }
    })();
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden text-[var(--text-primary)] selection:bg-[var(--accent)] selection:text-black">
      <div className="landing-bg" aria-hidden />
      <div className="noise-overlay" aria-hidden />

      <header className="absolute top-0 z-10 flex w-full items-center justify-between px-6 py-6 md:px-12">
        <div className="flex items-center gap-2 font-medium tracking-wide ui-text-secondary">
          <Terminal size={18} className="shrink-0 text-[var(--accent)]" aria-hidden />
          <span className="text-sm md:text-base">Nanobot Space</span>
        </div>
        <button
          type="button"
          onClick={openLogin}
          className="text-sm font-medium ui-text-secondary ui-motion-fast hover:text-[var(--text-primary)]"
        >
          登录控制台
        </button>
      </header>

      <main className="relative z-10 flex min-h-screen flex-col items-center justify-center px-4 pb-24 pt-20 text-center">
        <section className="flex w-full max-w-5xl flex-col items-center" aria-label="产品介绍">
          <div className="mb-8 inline-flex max-w-full cursor-default items-center rounded-full border border-[var(--border-strong)] bg-[var(--surface-2)]/30 px-4 py-1.5 text-xs font-medium ui-text-secondary shadow-sm backdrop-blur-md ui-motion-fast hover:bg-[var(--surface-2)]/50 md:text-sm">
            <span className="relative mr-2.5 flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent)]" />
            </span>
            AI应用使能组
          </div>

          <h1 className="mb-6 break-words bg-gradient-to-br from-[var(--text-primary)] via-[var(--text-secondary)] to-[var(--text-muted)] bg-clip-text text-5xl font-extrabold tracking-tight text-transparent drop-shadow-sm md:text-7xl lg:text-8xl xl:text-[8.5rem] leading-[1.05]">
            <span className="font-light tracking-normal">交付</span>{" "}
            <span className="font-extrabold">Claw</span>
          </h1>
          <p className="mb-12 max-w-2xl text-base font-medium tracking-[0.2em] ui-text-muted md:text-lg">数据驱动决策，行动引领未来。</p>
          <button
            type="button"
            onClick={openLogin}
            className="group relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-xl border border-[var(--border-strong)] bg-white/[0.03] px-8 py-3.5 text-sm font-medium ui-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-md ui-motion hover:border-[var(--text-muted)] hover:bg-white/[0.06]"
          >
            <span>进入系统</span>
            <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" aria-hidden />
          </button>
        </section>
      </main>

      <footer className="absolute bottom-6 z-10 w-full text-center text-xs ui-text-muted tracking-wider opacity-70">
        <p>© {new Date().getFullYear()} Huawei Technologies Co., Ltd. 保留一切权利</p>
      </footer>

      {isEntering ? (
        <div className={styles.enteringOverlay} aria-live="polite" aria-busy="true">
          <div className={styles.enteringSpinner} aria-hidden />
          <p className={styles.enteringText}>正在进入工作台…</p>
        </div>
      ) : null}

      <div
        className={`${styles.backdrop} ${loginOpen ? styles.backdropOpen : ""}`}
        role="presentation"
        onClick={closeLogin}
        aria-hidden={!loginOpen}
      />

      <div
        className={`${styles.panel} ${loginOpen ? styles.panelOpen : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="loginTitle"
      >
        <div className={styles.panelTop}>
          <h2 id="loginTitle" className={styles.panelTitle}>
            欢迎回来
          </h2>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={closeLogin}
            aria-label="关闭"
            disabled={isEntering}
          >
            ×
          </button>
        </div>
        <form className={styles.form} onSubmit={onSubmit}>
          <label className={styles.lbl} htmlFor="landing-user">
            用户名
          </label>
          <input
            className={styles.inp}
            id="landing-user"
            name="username"
            type="text"
            autoComplete="username"
            placeholder="工号或账号"
            value={username}
            onChange={(ev) => setUsername(ev.target.value)}
          />

          <label className={styles.lbl} htmlFor="landing-pass">
            密码
          </label>
          <input
            className={styles.inp}
            id="landing-pass"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
          />

          {loginError ? (
            <p className="mb-3 text-[13px] font-medium" style={{ color: "#f85149" }}>
              {loginError}
            </p>
          ) : null}

          <div className={styles.mid}>
            <label>
              <input
                type="checkbox"
                name="remember"
                checked={remember}
                onChange={(ev) => setRemember(ev.target.checked)}
              />
              记住我
            </label>
            <a href="#" onClick={(ev) => ev.preventDefault()}>
              忘记密码
            </a>
          </div>

          <button type="submit" className={styles.go} disabled={isEntering}>
            {isEntering ? "进入中…" : "登录"}
          </button>
          <p className={styles.reg}>
            还没有账号？{" "}
            <Link href="/register" className="font-medium underline-offset-2 hover:underline">
              立即注册
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
