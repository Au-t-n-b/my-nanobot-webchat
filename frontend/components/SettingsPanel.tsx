"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Eye, EyeOff, Loader2, Save, X } from "lucide-react";

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

export function SettingsPanel({ onClose }: { onClose: () => void }) {
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
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((t: ToastState) => {
    setToast(t);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast({ kind: "none" }), 3000);
  }, []);

  useEffect(() => {
    setLoading(true);
    fetch("/api/config")
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

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/config", {
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

  return (
    <aside className="ui-panel h-full rounded-2xl p-4 flex flex-col gap-4 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-secondary">
          设置 <span className="font-normal normal-case tracking-normal ui-text-muted">Settings</span>
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 ui-text-muted hover:text-[var(--text-primary)] hover:bg-[var(--surface-3)] transition-colors"
          aria-label="关闭设置"
        >
          <X size={14} />
        </button>
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
