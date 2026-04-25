"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getOrInitDefaultProject,
  grantWorkspaceAccess,
  writeGlobalProjectContext,
} from "@/lib/globalProjectContext";
import { hydrateAuthFromStorage, isAuthed, setAuthSession } from "@/lib/authStore";
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
    if (!isEntering) return;
    const t = window.setTimeout(() => setIsEntering(false), 3000);
    return () => window.clearTimeout(t);
  }, [isEntering]);

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
        router.replace("/workbench");
        window.setTimeout(() => {
          const p = window.location.pathname.replace(/\/$/, "") || "/";
          if (p !== "/workbench") {
            window.location.replace("/workbench");
          } else {
            setIsEntering(false);
          }
        }, 300);
      } catch (e) {
        setLoginError(e instanceof Error ? e.message : String(e));
        setIsEntering(false);
      }
    })();
  };

  return (
    <div className={styles.landingPage}>
      <div className={styles.bgRoot} aria-hidden />

      <header className={styles.header}>
        <button
          type="button"
          className={styles.btnGhost}
          onClick={() => {
            setLoginOpen(true);
            queueMicrotask(() => {
              prefetchWorkbenchShell(router);
            });
          }}
        >
          Get Started
        </button>
      </header>

      <main className={styles.pageMain}>
        <section className={styles.heroCopy} aria-label="产品介绍">
          <h1 className={styles.heroTitle}>交付Claw——作业管理·智慧工勘·建模仿真</h1>
          <p className={styles.heroSubtitle}>数据驱动决策，行动引领未来</p>
        </section>
      </main>

      <footer className={styles.siteFooter}>
        <p>版权所有 © 华为技术有限公司 2026 保留一切权利</p>
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
