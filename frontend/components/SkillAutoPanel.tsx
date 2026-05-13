"use client";

import { CheckCircle2, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

function aguiRequestPath(path: string): string {
  const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

type Status = "idle" | "loading" | "saving" | "success" | "error";

const DARWIN_DESC = "评估 → 改进 → 实测 → 确认/回滚。用户触发「优化skill」时执行进化循环，使用8维度评分 rubric + git 版本控制。";
const HERMES_DESC = "对话中即时修正 + 后台自动 review。累计 N 轮工具调用后，自动分析对话并创建或更新 skill。";

export function SkillAutoPanel({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [savedMsg, setSavedMsg] = useState("");
  const [form, setForm] = useState({
    darwinEnabled: false,
    hermesEnabled: false,
    hermesNudgeInterval: 10,
  });

  const loadConfig = useCallback(async () => {
    setStatus("loading");
    setErrorMsg("");
    try {
      const res = await fetch(aguiRequestPath("/api/config"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const cfg = await res.json();
      const sa = cfg?.skills_auto ?? {};
      setForm({
        darwinEnabled: Boolean(sa.darwin_enabled),
        hermesEnabled: Boolean(sa.hermes_enabled),
        hermesNudgeInterval: typeof sa.hermes_nudge_interval === "number" ? sa.hermes_nudge_interval : 10,
      });
      setStatus("idle");
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const handleSave = async () => {
    setErrorMsg("");
    setSavedMsg("");
    setStatus("saving");
    try {
      const patch = {
        skills_auto: {
          darwin_enabled: form.darwinEnabled,
          hermes_enabled: form.hermesEnabled,
          hermes_nudge_interval: form.hermesNudgeInterval,
        },
      };
      const res = await fetch(aguiRequestPath("/api/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (res.status === 409) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? "当前 AI 正在运行任务，请稍后再试");
      }
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      setStatus("success");
      setSavedMsg("Skill 自动管理设置已保存并生效");
      onSaved?.();
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "保存失败");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-auto px-4 py-4">
      <div className="flex flex-col gap-4 pb-6">
        {/* Header */}
        <div>
          <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            Skill 自动管理
          </h2>
          <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
            达尔文进化 + Hermes 自动创建
          </p>
        </div>

        {/* Status messages */}
        {errorMsg && (
          <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "rgb(248,113,113)" }}>
            {errorMsg}
          </div>
        )}
        {savedMsg && (
          <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(16,185,129,0.1)", color: "rgb(110,231,183)" }}>
            <CheckCircle2 size={14} />
            {savedMsg}
          </div>
        )}

        {/* Darwin toggle */}
        <section
          className="rounded-xl p-4 flex flex-col gap-3"
          style={{ background: "var(--surface-2)", border: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1">
              <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                达尔文 Skill 自动优化
              </div>
              <div className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
                {DARWIN_DESC}
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={form.darwinEnabled}
              onClick={() => setForm((p) => ({ ...p, darwinEnabled: !p.darwinEnabled }))}
              className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
              style={{
                background: form.darwinEnabled ? "var(--accent)" : "var(--surface-3)",
                boxShadow: "inset 0 0 0 1px var(--border-subtle)",
              }}
            >
              <span
                className="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                style={{ transform: form.darwinEnabled ? "translateX(16px)" : "translateX(0)" }}
              />
            </button>
          </div>
        </section>

        {/* Hermes toggle */}
        <section
          className="rounded-xl p-4 flex flex-col gap-3"
          style={{ background: "var(--surface-2)", border: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1">
              <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                Hermes Skill 自动创建
              </div>
              <div className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
                {HERMES_DESC}
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={form.hermesEnabled}
              onClick={() => setForm((p) => ({ ...p, hermesEnabled: !p.hermesEnabled }))}
              className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
              style={{
                background: form.hermesEnabled ? "var(--accent)" : "var(--surface-3)",
                boxShadow: "inset 0 0 0 1px var(--border-subtle)",
              }}
            >
              <span
                className="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                style={{ transform: form.hermesEnabled ? "translateX(16px)" : "translateX(0)" }}
              />
            </button>
          </div>

          {/* Hermes interval (only shown when enabled) */}
          {form.hermesEnabled && (
            <div className="flex flex-col gap-2 pt-1">
              <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                <span>Review 触发间隔</span>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={form.hermesNudgeInterval}
                    onChange={(e) => setForm((p) => ({ ...p, hermesNudgeInterval: Math.max(1, parseInt(e.target.value) || 10) }))}
                    className="w-20 rounded-lg px-2.5 py-1.5 text-xs ui-input ui-input-focusable"
                  />
                  <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                    轮工具调用后触发后台 review
                  </span>
                </div>
              </label>
            </div>
          )}
        </section>

        {/* Save button */}
        <button
          type="button"
          disabled={status === "saving" || status === "loading"}
          onClick={() => void handleSave()}
          className="mt-2 flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50"
          style={{
            background: status === "success" ? "rgba(16,185,129,0.15)" : "var(--accent)",
            color: status === "success" ? "rgb(110,231,183)" : "#fff",
          }}
        >
          {status === "saving" ? (
            "保存中…"
          ) : status === "success" ? (
            <>
              <CheckCircle2 size={16} />
              已保存
            </>
          ) : (
            <>
              <Save size={16} />
              保存设置
            </>
          )}
        </button>
      </div>
    </div>
  );
}
