"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, Rocket, Settings, Sparkles } from "lucide-react";
import { CenteredModal } from "@/components/CenteredModal";
import { PROVIDER_MODEL_SUGGESTIONS } from "@/lib/providerModelSuggestions";

const STORAGE_KEY = "setup_guide_completed";

function aguiRequestPath(path: string): string {
  const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

const PROVIDER_OPTIONS = Object.keys(PROVIDER_MODEL_SUGGESTIONS).map((key) => ({
  value: key,
  label: key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " "),
}));

type Step = 0 | 1 | 2;

export function SetupGuideDialog() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [provider, setProvider] = useState("zhipu");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [model, setModel] = useState("");

  const modelSuggestions = useMemo(
    () => PROVIDER_MODEL_SUGGESTIONS[provider]?.models ?? [],
    [provider],
  );

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(aguiRequestPath("/api/config"));
        if (!res.ok) { setLoading(false); return; }
        const cfg = await res.json();
        const providers = cfg?.providers ?? {};
        const hasKey = Object.values(providers).some((p: any) => {
          const k = p?.apiKey || p?.api_key || "";
          return typeof k === "string" && k.length > 0;
        });
        const hasModel = Boolean(cfg?.agents?.defaults?.model);
        if (!cancelled) {
          if (!hasKey || !hasModel) setOpen(true);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const suggestion = PROVIDER_MODEL_SUGGESTIONS[provider];
    if (suggestion) setModel(suggestion.defaultModel);
  }, [provider]);

  const handleSave = useCallback(async () => {
    if (!apiKey.trim()) { setSaveError("请输入 API Key"); return; }
    if (!model.trim()) { setSaveError("请输入模型名称"); return; }
    setSaving(true);
    setSaveError("");
    try {
      const patch = {
        agents: {
          defaults: { model: model.trim(), provider },
          models: modelSuggestions.length > 0 ? modelSuggestions : [model.trim()],
        },
        providers: {
          [provider]: {
            apiKey: apiKey.trim(),
            ...(apiBase.trim() ? { apiBase: apiBase.trim() } : {}),
          },
        },
      };
      const res = await fetch(aguiRequestPath("/api/config"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as any).detail ?? `HTTP ${res.status}`);
      }
      localStorage.setItem(STORAGE_KEY, "1");
      setOpen(false);
    } catch (err: any) {
      setSaveError(err?.message ?? "保存失败");
    } finally {
      setSaving(false);
    }
  }, [apiKey, apiBase, model, provider, modelSuggestions]);

  if (loading || !open) return null;

  const steps = [
    { label: "欢迎", icon: Sparkles },
    { label: "服务商", icon: Settings },
    { label: "模型", icon: Rocket },
  ];

  return (
    <CenteredModal
      open={open}
      onClose={() => {}}
      title="配置向导"
      disableDismiss
      panelClassName="w-full max-w-md"
    >
      <div className="flex flex-col gap-5">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2">
          {steps.map((s, i) => {
            const StepIcon = s.icon;
            const done = i < step;
            const active = i === step;
            return (
              <div key={s.label} className="flex items-center gap-2">
                <div
                  className="flex items-center justify-center rounded-full ui-motion-fast"
                  style={{
                    width: 32,
                    height: 32,
                    background: done
                      ? "var(--accent)"
                      : active
                        ? "color-mix(in oklab, var(--accent) 20%, transparent)"
                        : "var(--surface-2)",
                    border: active ? "2px solid var(--accent)" : "2px solid transparent",
                  }}
                >
                  {done ? (
                    <CheckCircle2 size={16} className="text-black" />
                  ) : (
                    <StepIcon size={14} style={{ color: active ? "var(--accent)" : "var(--text-muted)" }} />
                  )}
                </div>
                {i < steps.length - 1 && (
                  <ChevronRight size={14} style={{ color: "var(--text-muted)" }} />
                )}
              </div>
            );
          })}
        </div>

        {/* Step 0: Welcome */}
        {step === 0 && (
          <div className="flex flex-col items-center gap-4 py-4">
            <div
              className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              AI
            </div>
            <h2
              className="text-lg font-semibold text-center"
              style={{ color: "var(--text-primary)" }}
            >
              欢迎使用 交付claw
            </h2>
            <p className="text-center ui-text-body ui-text-secondary leading-relaxed px-2">
              只需两步即可完成初始配置：选择 AI 服务商并填写密钥，然后选择模型。之后你可以在设置中随时调整。
            </p>
            <button
              type="button"
              onClick={() => setStep(1)}
              className="ui-motion mt-2 inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-medium text-black bg-[var(--accent)] hover:brightness-110"
            >
              开始配置
              <ChevronRight size={16} />
            </button>
          </div>
        )}

        {/* Step 1: Provider + API Key */}
        {step === 1 && (
          <div className="flex flex-col gap-4">
            <div>
              <h3
                className="text-sm font-semibold mb-3"
                style={{ color: "var(--text-primary)" }}
              >
                选择 AI 服务商
              </h3>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none ui-motion-fast"
                style={{
                  borderColor: "var(--border-subtle)",
                  background: "var(--surface-2)",
                  color: "var(--text-primary)",
                }}
              >
                {PROVIDER_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium ui-text-secondary mb-1 block">
                API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="w-full rounded-lg border px-3 py-2 text-sm font-mono outline-none ui-motion-fast"
                style={{
                  borderColor: "var(--border-subtle)",
                  background: "var(--surface-2)",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            <div>
              <label className="text-xs font-medium ui-text-secondary mb-1 block">
                API Base URL
                <span className="text-[10px] ui-text-muted ml-1">（可选，使用默认值留空）</span>
              </label>
              <input
                type="text"
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
                placeholder="https://api.example.com/v1"
                className="w-full rounded-lg border px-3 py-2 text-sm font-mono outline-none ui-motion-fast"
                style={{
                  borderColor: "var(--border-subtle)",
                  background: "var(--surface-2)",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => {
                  if (!apiKey.trim()) { setSaveError("请输入 API Key"); return; }
                  setSaveError("");
                  setStep(2);
                }}
                className="ui-motion inline-flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-medium text-black bg-[var(--accent)] hover:brightness-110"
              >
                下一步
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Model selection */}
        {step === 2 && (
          <div className="flex flex-col gap-4">
            <div>
              <h3
                className="text-sm font-semibold mb-3"
                style={{ color: "var(--text-primary)" }}
              >
                选择模型
              </h3>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="模型名称"
                className="w-full rounded-lg border px-3 py-2 text-sm font-mono outline-none ui-motion-fast"
                style={{
                  borderColor: "var(--border-subtle)",
                  background: "var(--surface-2)",
                  color: "var(--text-primary)",
                }}
              />
            </div>

            {modelSuggestions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {modelSuggestions.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setModel(m)}
                    className="rounded-lg px-2.5 py-1 text-xs font-mono ui-motion-fast"
                    style={{
                      background: m === model ? "var(--accent)" : "var(--surface-2)",
                      color: m === model ? "#000" : "var(--text-secondary)",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    {m}
                  </button>
                ))}
              </div>
            )}

            {saveError && (
              <p className="text-xs" style={{ color: "var(--danger)" }}>
                {saveError}
              </p>
            )}

            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="ui-motion rounded-lg px-4 py-2 text-sm font-medium ui-text-secondary ui-hover-soft"
              >
                上一步
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="ui-motion inline-flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-medium text-black bg-[var(--accent)] hover:brightness-110 disabled:opacity-60"
              >
                {saving ? "保存中..." : "完成配置"}
                {!saving && <CheckCircle2 size={16} />}
              </button>
            </div>
          </div>
        )}
      </div>
    </CenteredModal>
  );
}
