"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Eye, EyeOff, Loader2, Minimize2, Save, X } from "lucide-react";
import { useWorkbenchStepperView } from "@/hooks/useWorkbenchStepperView";

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

type ProxyConfig = {
  enabled: boolean;
  host: string;
  port: string;
  username: string;
  password: string;
};

type Config = {
  proxy?: Partial<ProxyConfig>;
  [key: string]: unknown;
};

type ToastState =
  | { kind: "none" }
  | { kind: "success"; text: string }
  | { kind: "error"; text: string };

type RemoteSession = {
  connected: boolean;
  frontendBase: string;
  apiBase: string;
  user: { workId: string; name: string; role: string } | null;
  projects: Array<{ id: string; name: string }>;
  selectedProjectId: string | null;
  selectedProjectName: string | null;
};

export function SettingsPanel({
  onClose,
  onOpenRemoteUpload,
  showCloseButton = true,
}: {
  onClose: () => void;
  onOpenRemoteUpload?: () => void;
  /** 默认 true；若外层 Modal 已提供统一关闭按钮，可设为 false 避免重复 X */
  showCloseButton?: boolean;
}) {
  const [proxy, setProxy] = useState<ProxyConfig>({
    enabled: false,
    host: "",
    port: "8080",
    username: "",
    password: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<ToastState>({ kind: "none" });
  const [showPassword, setShowPassword] = useState(false);
  const [remoteSession, setRemoteSession] = useState<RemoteSession | null>(null);
  const [remoteForm, setRemoteForm] = useState({
    frontendBase: "http://127.0.0.1:3000",
    apiBase: "http://127.0.0.1:8000",
    workId: "",
    password: "",
  });
  const [remoteLoading, setRemoteLoading] = useState(true);
  const [remoteBusy, setRemoteBusy] = useState<"idle" | "login" | "logout" | "project">("idle");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { view: stepperView, setView: setStepperView } = useWorkbenchStepperView();

  const showToast = useCallback((t: ToastState) => {
    setToast(t);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast({ kind: "none" }), 3000);
  }, []);

  useEffect(() => {
    setLoading(true);
    fetch(aguiRequestPath("/api/config"))
      .then((r) => r.json())
      .then((data: Config) => {
        const p = data.proxy ?? {};
        setProxy({
          enabled: Boolean(p.enabled),
          host: typeof p.host === "string" ? p.host : "",
          port: typeof p.port === "string" ? p.port : p.port != null ? String(p.port) : "8080",
          username: typeof p.username === "string" ? p.username : "",
          password: typeof p.password === "string" ? p.password : "",
        });
      })
      .catch(() => {/* use defaults */})
      .finally(() => setLoading(false));
  }, []);

  const loadRemoteSession = useCallback(async () => {
    setRemoteLoading(true);
    try {
      const res = await fetch(aguiRequestPath("/api/remote-center/session"));
      const data = (await res.json().catch(() => ({}))) as Partial<RemoteSession>;
      setRemoteSession({
        connected: Boolean(data.connected),
        frontendBase: typeof data.frontendBase === "string" ? data.frontendBase : "",
        apiBase: typeof data.apiBase === "string" ? data.apiBase : "",
        user: data.user
          ? {
              workId: String(data.user.workId ?? ""),
              name: String(data.user.name ?? ""),
              role: String(data.user.role ?? ""),
            }
          : null,
        projects: Array.isArray(data.projects)
          ? data.projects.map((item) => ({ id: String(item.id), name: String(item.name) }))
          : [],
        selectedProjectId: typeof data.selectedProjectId === "string" ? data.selectedProjectId : null,
        selectedProjectName: typeof data.selectedProjectName === "string" ? data.selectedProjectName : null,
      });
      setRemoteForm((prev) => ({
        frontendBase: typeof data.frontendBase === "string" && data.frontendBase ? data.frontendBase : prev.frontendBase,
        apiBase: typeof data.apiBase === "string" && data.apiBase ? data.apiBase : prev.apiBase,
        workId: typeof data.user?.workId === "string" && data.user.workId ? data.user.workId : prev.workId,
        password: "",
      }));
    } catch {
      setRemoteSession(null);
    } finally {
      setRemoteLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRemoteSession();
  }, [loadRemoteSession]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(aguiRequestPath("/api/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proxy: {
            enabled: proxy.enabled,
            host: proxy.host,
            port: proxy.port,
            username: proxy.username,
            password: proxy.password,
          },
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({})) as { error?: string };
        throw new Error(d.error ?? `HTTP ${res.status}`);
      }
      showToast({ kind: "success", text: "配置已保存 ✓" });
    } catch (e) {
      showToast({ kind: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  const handleRemoteLogin = async () => {
    setRemoteBusy("login");
    try {
      const res = await fetch(aguiRequestPath("/api/remote-center/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(remoteForm),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: { message?: string } };
      if (!res.ok) {
        throw new Error(data.error?.message ?? `HTTP ${res.status}`);
      }
      showToast({ kind: "success", text: "远端中心登录成功 ✓" });
      await loadRemoteSession();
      setRemoteForm((prev) => ({ ...prev, password: "" }));
    } catch (e) {
      showToast({ kind: "error", text: e instanceof Error ? e.message : "远端登录失败" });
    } finally {
      setRemoteBusy("idle");
    }
  };

  const handleRemoteLogout = async () => {
    setRemoteBusy("logout");
    try {
      const res = await fetch(aguiRequestPath("/api/remote-center/logout"), { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast({ kind: "success", text: "已退出远端中心" });
      await loadRemoteSession();
    } catch (e) {
      showToast({ kind: "error", text: e instanceof Error ? e.message : "退出失败" });
    } finally {
      setRemoteBusy("idle");
    }
  };

  const handleProjectChange = async (projectId: string) => {
    setRemoteBusy("project");
    try {
      const res = await fetch(aguiRequestPath("/api/remote-center/project"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: { message?: string } };
      if (!res.ok) throw new Error(data.error?.message ?? `HTTP ${res.status}`);
      await loadRemoteSession();
      showToast({ kind: "success", text: "当前项目已切换" });
    } catch (e) {
      showToast({ kind: "error", text: e instanceof Error ? e.message : "切换项目失败" });
    } finally {
      setRemoteBusy("idle");
    }
  };

  return (
    <aside className="ui-panel h-full rounded-2xl p-4 flex flex-col gap-4 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
          设置 <span className="font-normal normal-case tracking-normal ui-text-muted">Settings</span>
        </span>
        {showCloseButton && (
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 ui-text-muted hover:text-[var(--text-primary)] hover:bg-[var(--surface-3)] transition-colors"
            aria-label="关闭设置"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Toast */}
      {toast.kind !== "none" && (
        <div
          className="rounded-xl px-3 py-2 text-xs flex items-center gap-2 shrink-0"
          style={
            toast.kind === "success"
              ? { background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.28)", color: "var(--success)" }
              : { background: "rgba(239,107,115,0.12)", border: "1px solid rgba(239,107,115,0.28)", color: "var(--danger)" }
          }
        >
          {toast.kind === "success" ? <Check size={12} /> : null}
          {toast.text}
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center gap-2 ui-text-muted text-sm">
          <Loader2 size={16} className="animate-spin" />
          加载中…
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-auto flex flex-col gap-4">
          <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
            <div>
              <p className="text-sm font-medium ui-text-primary">流程进度展示</p>
              <p className="text-[11px] ui-text-muted mt-0.5">与顶栏图钉/收起为同一项偏好，持久化在本机</p>
            </div>
            <div className="flex flex-col gap-2" role="radiogroup" aria-label="流程进度展示">
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-[var(--border-subtle)] px-3 py-2.5 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--accent)]">
                <input
                  type="radio"
                  name="nanobot-stepper-view"
                  className="shrink-0"
                  checked={stepperView === "compact"}
                  onChange={() => setStepperView("compact")}
                />
                <div className="min-w-0">
                  <p className="text-sm ui-text-primary">紧凑胶囊</p>
                  <p className="text-[11px] ui-text-muted">默认占一行，点击展开完整流程与悬停子任务</p>
                </div>
                <Minimize2 size={16} className="shrink-0 ui-text-muted" aria-hidden />
              </label>
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-[var(--border-subtle)] px-3 py-2.5 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--accent)]">
                <input
                  type="radio"
                  name="nanobot-stepper-view"
                  className="shrink-0"
                  checked={stepperView === "docked"}
                  onChange={() => setStepperView("docked")}
                />
                <div className="min-w-0">
                  <p className="text-sm ui-text-primary">顶栏常驻</p>
                  <p className="text-[11px] ui-text-muted">全宽步骤条始终可见，适合需随时盯盘全流程的场景</p>
                </div>
              </label>
            </div>
          </section>

          {/* Proxy Section */}
          <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium ui-text-primary">内网代理</p>
                <p className="text-[11px] ui-text-muted mt-0.5">Proxy</p>
              </div>
              {/* Toggle switch */}
              <button
                type="button"
                role="switch"
                aria-checked={proxy.enabled}
                onClick={() => setProxy((p) => ({ ...p, enabled: !p.enabled }))}
                className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                style={{ background: proxy.enabled ? "var(--accent)" : "var(--surface-3)", boxShadow: "inset 0 0 0 1px var(--border-subtle)" }}
              >
                <span
                  className="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                  style={{ transform: proxy.enabled ? "translateX(16px)" : "translateX(0)" }}
                />
              </button>
            </div>

            {proxy.enabled && (
              <div className="flex flex-col gap-2 pt-1">
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-2 flex flex-col gap-1">
                    <label className="text-[11px] ui-text-muted">主机 Host</label>
                    <input
                      type="text"
                      value={proxy.host}
                      onChange={(e) => setProxy((p) => ({ ...p, host: e.target.value }))}
                      placeholder="127.0.0.1"
                      className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[11px] ui-text-muted">端口 Port</label>
                    <input
                      type="text"
                      value={proxy.port}
                      onChange={(e) => setProxy((p) => ({ ...p, port: e.target.value }))}
                      placeholder="8080"
                      className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[11px] ui-text-muted">用户名（可选）</label>
                  <input
                    type="text"
                    value={proxy.username}
                    onChange={(e) => setProxy((p) => ({ ...p, username: e.target.value }))}
                    placeholder="username"
                    autoComplete="off"
                    className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[11px] ui-text-muted">密码（可选）</label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={proxy.password}
                      onChange={(e) => setProxy((p) => ({ ...p, password: e.target.value }))}
                      placeholder="••••••••"
                      autoComplete="new-password"
                      className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 pr-8 text-xs w-full"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 ui-text-muted hover:ui-text-secondary transition-colors"
                      aria-label={showPassword ? "隐藏密码" : "显示密码"}
                    >
                      {showPassword ? <EyeOff size={12} /> : <Eye size={12} />}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium ui-text-primary">远端交付中心</p>
                <p className="text-[11px] ui-text-muted mt-0.5">Remote Delivery Center</p>
              </div>
              <span
                className="rounded-full px-2 py-1 text-[10px]"
                style={{
                  background: remoteSession?.connected ? "rgba(34,197,94,0.12)" : "var(--surface-3)",
                  color: remoteSession?.connected ? "var(--success)" : "var(--text-tertiary)",
                }}
              >
                {remoteSession?.connected ? "已连接" : remoteLoading ? "加载中" : "未连接"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1">
                <label className="text-[11px] ui-text-muted">前端地址</label>
                <input
                  type="text"
                  value={remoteForm.frontendBase}
                  onChange={(e) => setRemoteForm((prev) => ({ ...prev, frontendBase: e.target.value }))}
                  className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[11px] ui-text-muted">后端地址</label>
                <input
                  type="text"
                  value={remoteForm.apiBase}
                  onChange={(e) => setRemoteForm((prev) => ({ ...prev, apiBase: e.target.value }))}
                  className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[11px] ui-text-muted">工号</label>
                <input
                  type="text"
                  value={remoteForm.workId}
                  onChange={(e) => setRemoteForm((prev) => ({ ...prev, workId: e.target.value }))}
                  className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[11px] ui-text-muted">密码</label>
                <input
                  type="password"
                  value={remoteForm.password}
                  onChange={(e) => setRemoteForm((prev) => ({ ...prev, password: e.target.value }))}
                  className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs"
                />
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleRemoteLogin()}
                disabled={remoteBusy !== "idle"}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                style={{ background: "var(--accent)" }}
              >
                {remoteBusy === "login" ? "登录中…" : "登录远端"}
              </button>
              <button
                type="button"
                onClick={() => void handleRemoteLogout()}
                disabled={remoteBusy !== "idle" || !remoteSession?.connected}
                className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
              >
                {remoteBusy === "logout" ? "退出中…" : "退出登录"}
              </button>
              <button
                type="button"
                onClick={onOpenRemoteUpload}
                disabled={!remoteSession?.connected}
                className="ui-btn-ghost rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
              >
                打开上传面板
              </button>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[11px] ui-text-muted">当前项目</label>
              <select
                value={remoteSession?.selectedProjectId ?? ""}
                onChange={(e) => void handleProjectChange(e.target.value)}
                disabled={!remoteSession?.connected || remoteBusy !== "idle"}
                className="ui-input ui-input-focusable rounded-lg px-2.5 py-1.5 text-xs disabled:opacity-50"
              >
                <option value="">未绑定项目</option>
                {(remoteSession?.projects ?? []).map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
              <p className="text-[11px] ui-text-muted">
                当前用户：{remoteSession?.user ? `${remoteSession.user.name} (${remoteSession.user.workId})` : "未登录"}
              </p>
            </div>
          </section>

          {/* More sections can be added here */}
          <div className="text-[11px] ui-text-muted px-1">
            配置保存至 <code className="ui-text-secondary">~/.nanobot/config.json</code>
          </div>
        </div>
      )}

      {/* Save button */}
      <div className="shrink-0">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={loading || saving}
          className="w-full rounded-xl px-4 py-2.5 text-sm font-medium text-white flex items-center justify-center gap-2 transition-opacity disabled:opacity-50"
          style={{ background: "var(--accent)" }}
        >
          {saving ? (
            <><Loader2 size={14} className="animate-spin" /> 保存中…</>
          ) : (
            <><Save size={14} /> 保存配置</>
          )}
        </button>
      </div>
    </aside>
  );
}
