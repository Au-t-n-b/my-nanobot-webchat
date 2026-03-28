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

export function ConfigPanel({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const [text, setText] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

      {/* Editor body */}
      <div className="flex-1 min-h-0 overflow-auto">
        {status === "loading" ? (
          <div className="flex items-center justify-center h-32 gap-2 ui-text-secondary text-sm">
            <div
              className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: "var(--border-subtle)", borderTopColor: "var(--accent)" }}
            />
            加载中…
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
        <button
          type="button"
          onClick={() => { setText(originalText); setStatus("idle"); setErrorMsg(""); }}
          disabled={!isDirty || status === "loading" || status === "saving"}
          className="flex items-center gap-1.5 text-xs ui-text-secondary hover:ui-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <RotateCcw size={12} />
          撤销更改
        </button>

        <div className="flex items-center gap-3">
          {isDirty && (
            <span className="text-[10px]" style={{ color: "var(--warning)" }}>
              未保存的更改
            </span>
          )}
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={status === "loading" || status === "saving" || !isDirty}
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
