"use client";

import { AlertCircle, CheckCircle2, Plus, RotateCcw, Save, Settings, Wifi, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { PROVIDER_MODEL_SUGGESTIONS } from "@/lib/providerModelSuggestions";

function aguiRequestPath(path: string): string {
  // Force direct-to-backend requests so config writes always trigger:
  // - schema validation
  // - provider build
  // - hot reload (reload_provider_and_model)
  const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
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

type AgentProfile = {
  name: string;
  provider: string;
  model: string;
  models: string[];
};

export function ConfigPanel({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const [mode, setMode] = useState<Mode>("form");
  const [text, setText] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [providers, setProviders] = useState<ProviderItem[]>([]);
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("");
  const [form, setForm] = useState({
    providerName: "zhipu",
    defaultModel: "glm-4.7",
    modelListText: "glm-4\nglm-4v\nglm-4.7\nglm-5",
    apiKey: "",
    apiKeyConfigured: false,
    apiBase: "",
    proxyEnabled: false,
    proxyUrl: "",
    sslVerify: true,
    syncModelProxy: false,
  });
  const [testStatus, setTestStatus] = useState<Status>("idle");
  const [testMsg, setTestMsg] = useState<string>("");
  const [savedMsg, setSavedMsg] = useState<string>("");
  const apiBaseTouchedRef = useRef(false);
  const lastAutoBaseRef = useRef<string>("");
  const modelTouchedRef = useRef(false);
  const modelsTouchedRef = useRef(false);

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
        agents?: { defaults?: { model?: string; provider?: string }; models?: string[]; profiles?: AgentProfile[] };
        providers?: Record<string, { apiKey?: string; api_key?: string; apiBase?: string; api_base?: string; proxy?: string | null }>;
        tools?: { web?: { proxy?: string | null; sslVerify?: boolean } };
      };
      if (Array.isArray(cfg?.agents?.profiles)) {
        const cleaned = cfg.agents.profiles
          .filter((p) => p && typeof p === "object")
          .map((p) => ({
            name: String((p as AgentProfile).name || "").trim(),
            provider: String((p as AgentProfile).provider || "auto").trim(),
            model: String((p as AgentProfile).model || "").trim(),
            models: Array.isArray((p as AgentProfile).models)
              ? (p as AgentProfile).models.map((x) => String(x || "").trim()).filter((x) => x)
              : [],
          }))
          .filter((p) => p.name);
        setProfiles(cleaned);
        setSelectedProfile((cur) => cur || (cleaned[0]?.name ?? ""));
      } else {
        setProfiles([]);
      }
      const forcedProvider = cfg?.agents?.defaults?.provider;
      const providerFromConfig = typeof forcedProvider === "string" && forcedProvider.trim() ? forcedProvider.trim() : null;
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
      setForm((prev) => {
        const effectiveProviderName = providerFromConfig ?? prev.providerName;
        const p = cfg?.providers?.[effectiveProviderName];
        const maskedKey = (p?.apiKey ?? p?.api_key) as unknown;
        const keyConfigured = typeof maskedKey === "string" && maskedKey === "******";
        const apiBase = ((p?.apiBase ?? p?.api_base) as unknown) ?? "";
        const baseFromConfig = typeof apiBase === "string" ? apiBase : "";
        const spec = providers.find((x) => x.name === effectiveProviderName);
        const defaultBase = (spec?.defaultApiBase || "").trim();
        const shouldAutoFill = !apiBaseTouchedRef.current && !baseFromConfig.trim() && defaultBase;
        const nextBase = shouldAutoFill ? defaultBase : baseFromConfig;
        if (shouldAutoFill) lastAutoBaseRef.current = defaultBase;
        const suggestion = PROVIDER_MODEL_SUGGESTIONS[effectiveProviderName];
        const web = cfg?.tools?.web ?? {};
        const webProxy = typeof web.proxy === "string" ? web.proxy.trim() : "";
        const webSslVerify = typeof web.sslVerify === "boolean" ? web.sslVerify : true;
        const providerProxyRaw = p?.proxy;
        const providerProxy = typeof providerProxyRaw === "string" ? providerProxyRaw.trim() : "";
        return {
          ...prev,
          providerName: effectiveProviderName,
          apiKeyConfigured: keyConfigured,
          apiBase: nextBase || prev.apiBase,
          defaultModel:
            typeof m === "string" && m.trim()
              ? m.trim()
              : (modelTouchedRef.current ? prev.defaultModel : (suggestion?.defaultModel ?? prev.defaultModel)),
          modelListText: Array.isArray(cfg?.agents?.models) && cfg.agents.models.length > 0
            ? prev.modelListText
            : (modelsTouchedRef.current ? prev.modelListText : (suggestion?.models?.length ? suggestion.models.join("\n") : prev.modelListText)),
          proxyEnabled: Boolean(webProxy),
          proxyUrl: webProxy || prev.proxyUrl,
          sslVerify: webSslVerify,
          syncModelProxy: Boolean(webProxy && providerProxy && webProxy === providerProxy),
        };
      });
      setStatus("idle");
      setTimeout(() => textareaRef.current?.focus(), 80);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "加载失败");
    }
  }, [providers]);

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

  // Ensure apiBase auto-fills once provider metadata arrives (first load).
  useEffect(() => {
    if (providers.length === 0) return;
    if (apiBaseTouchedRef.current) return;
    setForm((prev) => {
      if (prev.apiBase.trim()) return prev;
      const spec = providers.find((x) => x.name === prev.providerName);
      const defaultBase = (spec?.defaultApiBase || "").trim();
      if (!defaultBase) return prev;
      lastAutoBaseRef.current = defaultBase;
      return { ...prev, apiBase: defaultBase };
    });
  }, [providers]);

  const isDirty = text !== originalText;

  const handleSave = async () => {
    setErrorMsg("");
    setSavedMsg("");
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
      if (res.status === 409) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? "当前 AI 正在运行任务，请稍后再试");
      }
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const out = (await res.json().catch(() => ({}))) as { reloaded?: boolean; current_model?: string; current_provider?: string };
      const formatted = JSON.stringify(parsed, null, 2);
      setText(formatted);
      setOriginalText(formatted);
      setStatus("success");
      if (out?.reloaded && out?.current_model) {
        setSavedMsg(`配置已更新并热加载成功，当前：${out.current_provider ? `${out.current_provider} / ` : ""}${out.current_model}`);
      } else {
        setSavedMsg("配置已保存");
      }
      onSaved?.();
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleSaveForm = async () => {
    setErrorMsg("");
    setSavedMsg("");
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
    const proxyValue = form.proxyEnabled && form.proxyUrl.trim() ? form.proxyUrl.trim() : null;
    setStatus("saving");
    try {
      const models = form.modelListText
        .split(/\r?\n|,/g)
        .map((x) => x.trim())
        .filter((x) => x);
      // Auto-save a profile per provider so each provider's "defaults + common models"
      // can be switched quickly from the main UI.
      const nextProfiles: AgentProfile[] = [
        ...profiles.filter((p) => p.name !== providerName),
        { name: providerName, provider: providerName, model, models },
      ];
      const patch = {
        agents: { defaults: { model, provider: providerName }, models, profiles: nextProfiles },
        providers: {
          [providerName]: {
            apiKey: apiKeyToSend,
            apiBase: form.apiBase.trim() ? form.apiBase.trim() : undefined,
            proxy: form.syncModelProxy ? proxyValue : null,
          },
        },
        tools: {
          web: {
            proxy: proxyValue,
            sslVerify: form.sslVerify,
          },
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
      const out = (await res.json().catch(() => ({}))) as { reloaded?: boolean; current_model?: string; current_provider?: string };
      setForm((prev) => ({ ...prev, apiKey: "", apiKeyConfigured: true }));
      setProfiles(nextProfiles);
      setSelectedProfile(providerName);
      setStatus("success");
      if (out?.reloaded && out?.current_model) {
        setSavedMsg(`配置已更新并热加载成功，当前：${out.current_provider ? `${out.current_provider} / ` : ""}${out.current_model}`);
      } else {
        setSavedMsg("配置已保存");
      }
      onSaved?.();
      // Refresh JSON view / persisted state.
      await loadConfig();
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleTest = async () => {
    setErrorMsg("");
    setTestMsg("");
    const providerName = (form.providerName || "").trim();
    const model = form.defaultModel.trim();
    const apiKeyToSend =
      form.apiKey.trim()
        ? form.apiKey.trim()
        : form.apiKeyConfigured
          ? "******"
          : "";
    if (!providerName) {
      setTestStatus("error");
      setTestMsg("请选择提供商");
      return;
    }
    if (!apiKeyToSend) {
      setTestStatus("error");
      setTestMsg("请填写 API Key（首次测试必须填写）");
      return;
    }
    setTestStatus("saving");
    try {
      const res = await fetch(aguiRequestPath("/api/config/test"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          providerName,
          apiKey: apiKeyToSend,
          apiBase: form.apiBase.trim() ? form.apiBase.trim() : undefined,
          model: model || undefined,
        }),
      });
      if (res.status === 409) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? "当前 AI 正在运行任务，请稍后再试");
      }
      const body = (await res.json().catch(() => ({}))) as { ok?: boolean; detail?: string; latencyMs?: number; model?: string };
      if (!res.ok || body.ok === false) {
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const latency = typeof body.latencyMs === "number" ? `${body.latencyMs}ms` : "";
      const m = typeof body.model === "string" && body.model ? body.model : model;
      setTestStatus("success");
      setTestMsg(`连接成功${latency ? `（${latency}）` : ""}，模型：${m}`);
      setTimeout(() => setTestStatus("idle"), 2500);
    } catch (e) {
      setTestStatus("error");
      setTestMsg(e instanceof Error ? e.message : "测试失败");
    }
  };

  const handleTestJson = async () => {
    setErrorMsg("");
    setTestMsg("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setTestStatus("error");
      setTestMsg("JSON 格式错误，请检查后重试");
      return;
    }
    const cfg = parsed as {
      agents?: { defaults?: { provider?: unknown; model?: unknown } };
      providers?: Record<string, { apiKey?: unknown; api_key?: unknown; apiBase?: unknown; api_base?: unknown }>;
    };
    const providerName = String(cfg?.agents?.defaults?.provider ?? "").trim();
    const model = String(cfg?.agents?.defaults?.model ?? "").trim();
    if (!providerName) {
      setTestStatus("error");
      setTestMsg("请在 JSON 中设置 agents.defaults.provider（例如 zhipu）");
      return;
    }
    const p = cfg?.providers?.[providerName];
    const apiKey = String((p?.apiKey ?? p?.api_key) ?? "").trim();
    const apiBase = String((p?.apiBase ?? p?.api_base) ?? "").trim();
    if (!apiKey) {
      setTestStatus("error");
      setTestMsg(`请在 JSON 中设置 providers.${providerName}.apiKey（或 api_key）`);
      return;
    }
    setTestStatus("saving");
    try {
      const res = await fetch(aguiRequestPath("/api/config/test"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          providerName,
          apiKey,
          apiBase: apiBase ? apiBase : undefined,
          model: model ? model : undefined,
        }),
      });
      if (res.status === 409) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? "当前 AI 正在运行任务，请稍后再试");
      }
      const body = (await res.json().catch(() => ({}))) as { ok?: boolean; detail?: string; latencyMs?: number; model?: string };
      if (!res.ok || body.ok === false) {
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const latency = typeof body.latencyMs === "number" ? `${body.latencyMs}ms` : "";
      const m = typeof body.model === "string" && body.model ? body.model : (model || "");
      setTestStatus("success");
      setTestMsg(`连接成功${latency ? `（${latency}）` : ""}${m ? `，模型：${m}` : ""}`);
      setTimeout(() => setTestStatus("idle"), 2500);
    } catch (e) {
      setTestStatus("error");
      setTestMsg(e instanceof Error ? e.message : "测试失败");
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
          {savedMsg || "配置已保存"}
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
                配置方案（Profiles）
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={selectedProfile}
                  onChange={(e) => setSelectedProfile(e.target.value)}
                  className="flex-1 rounded-lg border px-2 py-1.5 text-xs"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                >
                  <option value="">（未选择）</option>
                  {profiles.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name} — {p.provider} / {p.model}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold ui-text-secondary hover:ui-text-primary transition-colors"
                  style={{ background: "var(--surface-3)", border: "1px solid var(--border-subtle)" }}
                  disabled={!selectedProfile || status === "saving"}
                  title="应用所选方案并热加载"
                  onClick={async () => {
                    const p = profiles.find((x) => x.name === selectedProfile);
                    if (!p) return;
                    // Apply by patching defaults + quick-switch list; providers keys already live under providers.*
                    setStatus("saving");
                    setErrorMsg("");
                    setSavedMsg("");
                    try {
                      const patch = { agents: { defaults: { provider: p.provider, model: p.model }, models: p.models } };
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
                      const out = (await res.json().catch(() => ({}))) as { reloaded?: boolean; current_model?: string; current_provider?: string };
                      setStatus("success");
                      if (out?.reloaded && out?.current_model) {
                        setSavedMsg(`已切换方案并热加载，当前：${out.current_provider ? `${out.current_provider} / ` : ""}${out.current_model}`);
                      } else {
                        setSavedMsg("已切换方案");
                      }
                      // Refresh UI state from persisted config
                      await loadConfig();
                      onSaved?.();
                      setTimeout(() => setStatus("idle"), 2500);
                    } catch (e) {
                      setStatus("error");
                      setErrorMsg(e instanceof Error ? e.message : "切换失败");
                    }
                  }}
                >
                  应用
                </button>
                <button
                  type="button"
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold ui-text-secondary hover:ui-text-primary transition-colors"
                  style={{ background: "var(--surface-3)", border: "1px solid var(--border-subtle)" }}
                  disabled={status === "saving"}
                  title="将当前表单保存为一个方案（仅保存 provider/model/models）"
                  onClick={async () => {
                    const name = window.prompt("方案名称（例如：百炼-Qwen / Zhipu-GLM）")?.trim();
                    if (!name) return;
                    const provider = (form.providerName || "").trim();
                    const model = (form.defaultModel || "").trim();
                    const models = (form.modelListText || "")
                      .split(/\r?\n|,/g)
                      .map((x) => x.trim())
                      .filter((x) => x);
                    const nextProfiles = [
                      ...profiles.filter((p) => p.name !== name),
                      { name, provider, model, models },
                    ];
                    // Persist profiles into config.json
                    setStatus("saving");
                    setErrorMsg("");
                    setSavedMsg("");
                    try {
                      const patch = { agents: { profiles: nextProfiles } };
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
                      setProfiles(nextProfiles);
                      setSelectedProfile(name);
                      setStatus("success");
                      setSavedMsg(`已保存方案：${name}`);
                      await loadConfig();
                      setTimeout(() => setStatus("idle"), 2500);
                    } catch (e) {
                      setStatus("error");
                      setErrorMsg(e instanceof Error ? e.message : "保存方案失败");
                    }
                  }}
                >
                  保存为方案
                </button>
              </div>
              <div className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                方案只保存：provider / 默认模型 / 右上角常用模型列表。API Key 与 API Base 仍保存在 providers.* 中，不会重复存两份。
              </div>
            </section>
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
                    apiBaseTouchedRef.current = false;
                    lastAutoBaseRef.current = "";
                    setTestStatus("idle");
                    setTestMsg("");
                    modelTouchedRef.current = false;
                    modelsTouchedRef.current = false;
                    setForm((prev) => {
                      const spec = providers.find((x) => x.name === next);
                      const defaultBase = (spec?.defaultApiBase || "").trim();
                      const nextBase = defaultBase || "";
                      if (nextBase) lastAutoBaseRef.current = nextBase;
                      return { ...prev, providerName: next, apiKey: "", apiKeyConfigured: false, apiBase: nextBase };
                    });
                    // Re-hydrate from loaded config text (masked) for the newly selected provider
                    try {
                      const cfg = JSON.parse(text) as unknown;
                      const providersObj =
                        cfg && typeof cfg === "object" && "providers" in (cfg as Record<string, unknown>)
                          ? ((cfg as Record<string, unknown>).providers as Record<string, unknown> | undefined)
                          : undefined;
                      const p = providersObj && typeof providersObj === "object"
                        ? (providersObj[next] as Record<string, unknown> | undefined)
                        : undefined;
                      const maskedKey = p?.apiKey ?? p?.api_key;
                      const keyConfigured = typeof maskedKey === "string" && maskedKey === "******";
                      const apiBase = p?.apiBase ?? p?.api_base;
                      const fromConfig = typeof apiBase === "string" ? apiBase : "";
                      const spec = providers.find((x) => x.name === next);
                      const defaultBase = (spec?.defaultApiBase || "").trim();
                      const shouldAutoFill = !fromConfig.trim() && defaultBase;
                      const nextBase = shouldAutoFill ? defaultBase : fromConfig;
                      if (shouldAutoFill) lastAutoBaseRef.current = defaultBase;
                      const suggestion = PROVIDER_MODEL_SUGGESTIONS[next];
                      setForm((prev) => ({
                        ...prev,
                        providerName: next,
                        apiKeyConfigured: keyConfigured,
                        apiBase: nextBase,
                        defaultModel: (prev.defaultModel.trim() && modelTouchedRef.current)
                          ? prev.defaultModel
                          : (suggestion?.defaultModel ?? prev.defaultModel),
                        modelListText: (prev.modelListText.trim() && modelsTouchedRef.current)
                          ? prev.modelListText
                          : (suggestion?.models?.length ? suggestion.models.join("\n") : prev.modelListText),
                      }));
                    } catch {
                      const spec = providers.find((x) => x.name === next);
                      const defaultBase = (spec?.defaultApiBase || "").trim();
                      const suggestion = PROVIDER_MODEL_SUGGESTIONS[next];
                      if (defaultBase || suggestion) {
                        lastAutoBaseRef.current = defaultBase;
                        setForm((prev) => ({
                          ...prev,
                          providerName: next,
                          apiBase: defaultBase,
                          defaultModel: (prev.defaultModel.trim() && modelTouchedRef.current)
                            ? prev.defaultModel
                            : (suggestion?.defaultModel ?? prev.defaultModel),
                          modelListText: (prev.modelListText.trim() && modelsTouchedRef.current)
                            ? prev.modelListText
                            : (suggestion?.models?.length ? suggestion.models.join("\n") : prev.modelListText),
                        }));
                      }
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
                <div className="flex items-center gap-2">
                  <input
                    value={form.defaultModel}
                    onChange={(e) => {
                      modelTouchedRef.current = true;
                      setForm((prev) => ({ ...prev, defaultModel: e.target.value }));
                    }}
                    className="flex-1 rounded-lg border px-2 py-1.5 text-xs"
                    style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                    placeholder="例如：glm-4.7"
                  />
                  <button
                    type="button"
                    className="rounded-lg px-2.5 py-1.5 text-xs font-semibold ui-text-secondary hover:ui-text-primary transition-colors"
                    style={{ background: "var(--surface-3)", border: "1px solid var(--border-subtle)" }}
                    title="加入右上角常用模型列表"
                    onClick={() => {
                      const m = (form.defaultModel || "").trim();
                      if (!m) return;
                      const lines = (form.modelListText || "")
                        .split(/\r?\n|,/g)
                        .map((x) => x.trim())
                        .filter((x) => x);
                      const next = Array.from(new Set([m, ...lines]));
                      modelsTouchedRef.current = true;
                      setForm((prev) => ({ ...prev, modelListText: next.join("\n") }));
                    }}
                  >
                    <Plus size={12} />
                  </button>
                </div>
                <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                  配好 key 后，你只需要在右上角切换模型名（glm-4 / glm-4v / glm-4.7 / glm-5 等）
                </span>
              </label>

              <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                <span>右上角模型列表（每行一个）</span>
                <textarea
                  value={form.modelListText}
                  onChange={(e) => {
                    modelsTouchedRef.current = true;
                    setForm((prev) => ({ ...prev, modelListText: e.target.value }));
                  }}
                  className="rounded-lg border px-2 py-1.5 text-xs font-mono min-h-[96px] resize-y"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                  placeholder={"glm-4\nglm-4v\nglm-4.7\nglm-5"}
                />
              </label>
            </section>

            <section
              className="rounded-xl p-4 flex flex-col gap-3"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border-subtle)" }}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    内网代理
                  </div>
                  <div className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                    tools.web.proxy / sslVerify
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={form.proxyEnabled}
                  onClick={() => {
                    setForm((prev) => {
                      const nextEnabled = !prev.proxyEnabled;
                      const proxyExample = "http://工号:密码@proxyhk.huawei.com:8088";
                      const nextProxyUrl =
                        nextEnabled && !prev.proxyUrl.trim()
                          ? proxyExample
                          : (nextEnabled ? prev.proxyUrl : "");
                      return {
                        ...prev,
                        proxyEnabled: nextEnabled,
                        proxyUrl: nextProxyUrl,
                        syncModelProxy: nextEnabled ? prev.syncModelProxy : false,
                      };
                    });
                  }}
                  className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                  style={{
                    background: form.proxyEnabled ? "var(--accent)" : "var(--surface-3)",
                    boxShadow: "inset 0 0 0 1px var(--border-subtle)",
                  }}
                >
                  <span
                    className="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                    style={{ transform: form.proxyEnabled ? "translateX(16px)" : "translateX(0)" }}
                  />
                </button>
              </div>

              {form.proxyEnabled && (
                <div className="flex flex-col gap-3 pt-1">
                  <label className="flex flex-col gap-1 text-xs ui-text-secondary">
                    <span>完整代理 URL</span>
                    <input
                      type="text"
                      value={form.proxyUrl}
                      onChange={(e) => setForm((prev) => ({ ...prev, proxyUrl: e.target.value }))}
                      placeholder="http://工号:密码@proxyhk.huawei.com:8088"
                      className="rounded-lg px-2.5 py-1.5 text-xs ui-input ui-input-focusable"
                    />
                  </label>
                  <div className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                    示例：<code className="font-mono">http://工号:密码@proxyhk.huawei.com:8088</code>
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                        关闭 SSL 证书校验
                      </span>
                      <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                        对应 tools.web.sslVerify = false（内网代理常用）
                      </span>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={!form.sslVerify}
                      onClick={() => setForm((prev) => ({ ...prev, sslVerify: !prev.sslVerify }))}
                      className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                      style={{
                        background: !form.sslVerify ? "var(--accent)" : "var(--surface-3)",
                        boxShadow: "inset 0 0 0 1px var(--border-subtle)",
                      }}
                    >
                      <span
                        className="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                        style={{ transform: !form.sslVerify ? "translateX(16px)" : "translateX(0)" }}
                      />
                    </button>
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                        全局模型 API 走相同代理
                      </span>
                      <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                        写入 providers[{form.providerName || "…"}].proxy
                      </span>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={form.syncModelProxy}
                      onClick={() => setForm((prev) => ({ ...prev, syncModelProxy: !prev.syncModelProxy }))}
                      className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none"
                      style={{
                        background: form.syncModelProxy ? "var(--accent)" : "var(--surface-3)",
                        boxShadow: "inset 0 0 0 1px var(--border-subtle)",
                      }}
                    >
                      <span
                        className="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200"
                        style={{ transform: form.syncModelProxy ? "translateX(16px)" : "translateX(0)" }}
                      />
                    </button>
                  </div>
                </div>
              )}
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
                  onChange={(e) => {
                    apiBaseTouchedRef.current = true;
                    setForm((prev) => ({ ...prev, apiBase: e.target.value }));
                  }}
                  className="rounded-lg border px-2 py-1.5 text-xs font-mono"
                  style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)", color: "var(--text-primary)" }}
                  placeholder="例如：https://open.bigmodel.cn/api/paas/v4"
                />
              </label>
              {testMsg && (
                <div
                  className="text-[11px] leading-relaxed"
                  style={{
                    color:
                      testStatus === "error"
                        ? "rgb(252,165,165)"
                        : testStatus === "success"
                          ? "rgb(110,231,183)"
                          : "var(--text-tertiary)",
                  }}
                >
                  {testMsg}
                </div>
              )}
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
          {mode === "form" && (
            <button
              type="button"
              onClick={() => void handleTest()}
              disabled={status === "loading" || status === "saving" || testStatus === "saving"}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold ui-text-secondary hover:ui-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              style={{
                background: "var(--surface-3)",
                border: "1px solid var(--border-subtle)",
              }}
              title="测试连接（不会保存配置）"
            >
              {testStatus === "saving" ? (
                <>
                  <div className="w-3 h-3 border-2 border-white/20 border-t-white/70 rounded-full animate-spin" />
                  测试中…
                </>
              ) : (
                <>
                  <Wifi size={12} />
                  测试连接
                </>
              )}
            </button>
          )}
          {mode === "json" && (
            <button
              type="button"
              onClick={() => void handleTestJson()}
              disabled={status === "loading" || status === "saving" || testStatus === "saving"}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold ui-text-secondary hover:ui-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              style={{
                background: "var(--surface-3)",
                border: "1px solid var(--border-subtle)",
              }}
              title="测试连接（不会保存配置）"
            >
              {testStatus === "saving" ? (
                <>
                  <div className="w-3 h-3 border-2 border-white/20 border-t-white/70 rounded-full animate-spin" />
                  测试中…
                </>
              ) : (
                <>
                  <Wifi size={12} />
                  测试连接
                </>
              )}
            </button>
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
