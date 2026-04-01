"use client";

import { AlertCircle, CheckCircle2, RotateCcw, Save, Settings, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

type Status = "idle" | "loading" | "saving" | "success" | "error";
type Mode = "form" | "json";

type ProviderItem = {
  name: string;
  label: string;
  keywords: string[];
  isGateway: boolean;
  isLocal: boolean;
  isOAuth: boolean;
  isDirect: boolean;
  defaultApiBase: string;
  litellmPrefix: string;
  stripModelPrefix: boolean;
};

export function ConfigPanel({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const [mode, setMode] = useState<Mode>("form");
  const [text, setText] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [providers, setProviders] = useState<ProviderItem[]>([]);
  const [form, setForm] = useState({
    providerName: "zhipu",
    defaultModel: "glm-4.7",
    modelListText: "glm-4\nglm-4v\nglm-4.7\nglm-5",
    apiKey: "",
    apiKeyConfigured: false,
    apiBase: "",
  });

  const loadConfig = useCallback(async () => {
    setStatus("loading");
    setErrorMsg("");
    try {
      const res = await fetch(aguiRequestPath("/api/config"));
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const json = await res.json();
      const formatted = JSON.stringify(json, null, 2);
      setText(formatted);
      setOriginalText(formatted);
      // Best-effort: hydrate form fields from config (apiKey is masked server-side).
      const cfg = json as {
        agents?: { defaults?: { model?: string }; models?: string[] };
        providers?: Record<string, { apiKey?: string; api_key?: string; apiBase?: string; api_base?: string }>;
      };
      const m = cfg?.agents?.defaults?.model;
      if (typeof m === "string" && m.trim()) {
        setForm((prev) => ({ ...prev, defaultModel: m.trim() }));
      }
      if (Array.isArray(cfg?.agents?.models)) {
        const cleaned = cfg.agents.models
          .map((x) => (typeof x === "string" ? x.trim() : ""))
          .filter((x) => x);
        if (cleaned.length > 0) {
          setForm((prev) => ({ ...prev, modelListText: cleaned.join("\n") }));
        }
      }
      const pName = form.providerName;
      const p = cfg?.providers?.[pName];
      const maskedKey = (p?.apiKey ?? p?.api_key) as unknown;
      const keyConfigured = typeof maskedKey === "string" && maskedKey === "******";
      const apiBase = ((p?.apiBase ?? p?.api_base) as unknown) ?? "";
      setForm((prev) => ({
        ...prev,
        apiKeyConfigured: keyConfigured,
        apiBase: typeof apiBase === "string" ? apiBase : prev.apiBase,
      }));
      setStatus("idle");
      setTimeout(() => textareaRef.current?.focus(), 80);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const loadProviders = useCallback(async () => {
    try {
      const res = await fetch(aguiRequestPath("/api/providers"));
      if (!res.ok) return;
      const j = (await res.json()) as { providers?: ProviderItem[] };
      if (Array.isArray(j.providers)) setProviders(j.providers);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void loadProviders();
  }, [loadProviders]);

  const isDirty = text !== originalText;

  const handleSave = async () => {
    setErrorMsg("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setStatus("error");
      setErrorMsg("JSON 格式错误，请检查后重试");
      return;
    }
    setStatus("saving");
    try {
      const res = await fetch(aguiRequestPath("/api/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const formatted = JSON.stringify(parsed, null, 2);
      setText(formatted);
      setOriginalText(formatted);
      setStatus("success");
      onSaved?.();
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleSaveForm = async () => {
    setErrorMsg("");
    const model = form.defaultModel.trim();
    if (!model) {
      setStatus("error");
      setErrorMsg("请填写默认模型，例如 glm-4.7");
      return;
    }
    const providerName = (form.providerName || "").trim();
    if (!providerName) {
      setStatus("error");
      setErrorMsg("请选择模型提供商");
      return;
    }
    const apiKeyToSend =
      form.apiKey.trim()
        ? form.apiKey.trim()
        : form.apiKeyConfigured
          ? "******"
          : "";
    if (!apiKeyToSend) {
      setStatus("error");
      setErrorMsg("请填写 API Key（首次配置必须填写）");
      return;
    }
    setStatus("saving");
    try {
      const models = form.modelListText
        .split(/\r?\n|,/g)
        .map((x) => x.trim())
        .filter((x) => x);
      const patch = {
        agents: { defaults: { model }, models },
        providers: {
          [providerName]: {
            apiKey: apiKeyToSend,
            apiBase: form.apiBase.trim() ? form.apiBase.trim() : undefined,
          },
        },
      };
      const res = await fetch(aguiRequestPath("/api/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      setForm((prev) => ({ ...prev, apiKey: "", apiKeyConfigured: true }));
      setStatus("success");
      onSaved?.();
      // Refresh JSON view / persisted state.
      await loadConfig();
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "保存失败");
    }
  };

  return (
    <div className="h-full flex flex-col min-h-0" style={{ background: "var(--surface-1)" }}>
      {/* Panel header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-center gap-2">
          <Settings size={14} className="ui-text-secondary" />
          <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            配置中心
          </span>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{
              background: "var(--surface-3)",
              color: "var(--text-tertiary)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            ~/.nanobot/config.json
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="rounded-lg p-1.5 ui-text-secondary hover:ui-text-primary transition-colors"
          style={{ background: "transparent" }}
        >
          <X size={15} />
        </button>
      </div>

      {/* Mode tabs */}
      <div
        className="flex items-center gap-2 px-4 py-2 shrink-0 text-xs"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--surface-2)" }}
      >
        <button
          type="button"
          onClick={() => setMode("form")}
          className="rounded-lg px-2.5 py-1 transition-colors"
          style={{
            background: mode === "form" ? "var(--surface-3)" : "transparent",
            border: "1px solid var(--border-subtle)",
            color: mode === "form" ? "var(--text-primary)" : "var(--text-tertiary)",
          }}
        >
          表单配置
        </button>
        <button
          type="button"
          onClick={() => setMode("json")}
          className="rounded-lg px-2.5 py-1 transition-colors"
          style={{
            background: mode === "json" ? "var(--surface-3)" : "transparent",
            border: "1px solid var(--border-subtle)",
            color: mode === "json" ? "var(--text-primary)" : "var(--text-tertiary)",
          }}
        >
          JSON
        </button>
        <div className="flex-1" />
        {mode === "form" && (
          <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
            保存后会热加载，可直接在右上角切换模型
          </span>
        )}
      </div>

      {/* Status banner */}
      {status === "error" && errorMsg && (
        <div
          className="flex items-center gap-2 px-4 py-2.5 shrink-0 text-xs"
          style={{
            background: "rgba(239,68,68,0.08)",
            borderBottom: "1px solid rgba(239,68,68,0.2)",
            color: "rgb(252,165,165)",
          }}
        >
          <AlertCircle size={13} className="shrink-0" />
          {errorMsg}
        </div>
      )}
      {status === "success" && (
        <div
          className="flex items-center gap-2 px-4 py-2.5 shrink-0 text-xs"
          style={{
            background: "rgba(16,185,129,0.08)",
            borderBottom: "1px solid rgba(16,185,129,0.2)",
            color: "rgb(110,231,183)",
          }}
        >
          <CheckCircle2 size={13} className="shrink-0" />
          配置已保存
        </div>
      )}

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-auto">
        {status === "loading" ? (
          <div className="flex items-center justify-center h-32 gap-2 ui-text-secondary text-sm">
            <div
              className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: "var(--border-subtle)", borderTopColor: "var(--accent)" }}
            />
            加载中…
          </div>
        ) : mode === "form" ? (
          <div className="p-4 flex flex-col gap-4">
            <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
              <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                模型与提供商
              </div>
              <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                <span>提供商</span>
                <select
                  value={form.providerName}
                  onChange={(e) => {
                    const next = e.target.value;
                    setForm((prev) => ({ ...prev, providerName: next, apiKey: "", apiKeyConfigured: false, apiBase: "" }));
                    // Re-hydrate from loaded config text (masked) for the newly selected provider
                    try {
                      const cfg = JSON.parse(text) as any;
                      const p = cfg?.providers?.[next];
                      const maskedKey = p?.apiKey ?? p?.api_key;
                      const keyConfigured = typeof maskedKey === "string" && maskedKey === "******";
                      const apiBase = p?.apiBase ?? p?.api_base;
                      setForm((prev) => ({
                        ...prev,
                        providerName: next,
                        apiKeyConfigured: keyConfigured,
                        apiBase: typeof apiBase === "string" ? apiBase : "",
                      }));
                    } catch {
                      // ignore
                    }
                  }}
                  className="rounded-lg border px-2 py-1.5 text-xs"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                >
                  {(providers.length > 0 ? providers : [{ name: "zhipu", label: "Zhipu AI", keywords: [], isGateway: false, isLocal: false, isOAuth: false, isDirect: false, defaultApiBase: "", litellmPrefix: "zai", stripModelPrefix: false }]).map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.label} ({p.name})
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                <span>默认模型</span>
                <input
                  value={form.defaultModel}
                  onChange={(e) => setForm((prev) => ({ ...prev, defaultModel: e.target.value }))}
                  className="rounded-lg border px-2 py-1.5 text-xs"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                  placeholder="例如：glm-4.7"
                />
                <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                  配好 key 后，你只需要在右上角切换模型名（glm-4 / glm-4v / glm-4.7 / glm-5 等）
                </span>
              </label>

              <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                <span>右上角模型列表（每行一个）</span>
                <textarea
                  value={form.modelListText}
                  onChange={(e) => setForm((prev) => ({ ...prev, modelListText: e.target.value }))}
                  className="rounded-lg border px-2 py-1.5 text-xs font-mono min-h-[96px] resize-y"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                  placeholder={"glm-4\nglm-4v\nglm-4.7\nglm-5"}
                />
              </label>
            </section>

            <section className="ui-card rounded-xl p-4 flex flex-col gap-3">
              <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                API 凭证
              </div>
              <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                <span>
                  API Key{" "}
                  {form.apiKeyConfigured && (
                    <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                      （已配置；留空则保持不变）
                    </span>
                  )}
                </span>
                <input
                  value={form.apiKey}
                  onChange={(e) => setForm((prev) => ({ ...prev, apiKey: e.target.value }))}
                  className="rounded-lg border px-2 py-1.5 text-xs font-mono"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                  placeholder={form.apiKeyConfigured ? "******" : "请输入 API Key"}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                <span>API Base（可选）</span>
                <input
                  value={form.apiBase}
                  onChange={(e) => setForm((prev) => ({ ...prev, apiBase: e.target.value }))}
                  className="rounded-lg border px-2 py-1.5 text-xs font-mono"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                  placeholder="例如：https://open.bigmodel.cn/api/paas/v4"
                />
              </label>
            </section>
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              if (status !== "idle") { setStatus("idle"); setErrorMsg(""); }
            }}
            spellCheck={false}
            className="w-full h-full min-h-[400px] resize-none font-mono text-xs leading-relaxed focus:outline-none"
            style={{
              background: "transparent",
              color: "var(--text-primary)",
              padding: "1rem",
            }}
            placeholder="{}"
            aria-label="config.json 内容"
          />
        )}
      </div>

      {/* Footer toolbar */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderTop: "1px solid var(--border-subtle)", background: "var(--surface-2)" }}
      >
        {mode === "json" ? (
          <button
            type="button"
            onClick={() => { setText(originalText); setStatus("idle"); setErrorMsg(""); }}
            disabled={!isDirty || status === "loading" || status === "saving"}
            className="flex items-center gap-1.5 text-xs ui-text-secondary hover:ui-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <RotateCcw size={12} />
            撤销更改
          </button>
        ) : (
          <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
            提示：API Key 不会回显；保存时留空表示保持原值
          </span>
        )}

        <div className="flex items-center gap-3">
          {mode === "json" && isDirty && (
            <span className="text-[10px]" style={{ color: "var(--warning)" }}>
              未保存的更改
            </span>
          )}
          <button
            type="button"
            onClick={() => void (mode === "json" ? handleSave() : handleSaveForm())}
            disabled={status === "loading" || status === "saving" || (mode === "json" && !isDirty)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ background: isDirty ? "var(--accent)" : "var(--surface-3)" }}
          >
            {status === "saving" ? (
              <>
                <div className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                保存中…
              </>
            ) : (
              <>
                <Save size={12} />
                保存配置
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
