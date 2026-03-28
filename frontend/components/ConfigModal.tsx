"use client";

import { Settings, X, Save, RotateCcw, AlertCircle, CheckCircle2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

function aguiRequestPath(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

type Status = "idle" | "loading" | "saving" | "success" | "error";

export function ConfigModal() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
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
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    if (open) {
      void loadConfig();
      // Focus textarea after transition
      setTimeout(() => textareaRef.current?.focus(), 150);
    }
  }, [open, loadConfig]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    if (open) window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  const isDirty = text !== originalText;

  const handleSave = async () => {
    setErrorMsg("");
    // Validate JSON before sending
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
      setOriginalText(text);
      setStatus("success");
      // Auto-clear success banner after 2.5 s
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleReset = () => {
    setText(originalText);
    setStatus("idle");
    setErrorMsg("");
  };

  return (
    <>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="配置中心"
        title="配置中心"
        className="rounded-lg p-2 ui-text-secondary hover:bg-[var(--surface-3)] hover:ui-text-primary transition-colors border border-transparent hover:border-[var(--border-subtle)]"
      >
        <Settings size={17} />
      </button>

      {/* Backdrop + Modal */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          aria-modal="true"
          role="dialog"
          aria-label="配置中心"
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />

          {/* Panel */}
          <div className="relative z-10 w-full max-w-2xl flex flex-col rounded-2xl border border-white/[0.05] bg-[#050505] shadow-[0_0_50px_rgba(0,0,0,0.8)] overflow-hidden max-h-[85dvh]">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.05] shrink-0">
              <div className="flex items-center gap-2.5">
                <Settings size={16} className="text-slate-400" />
                <span className="font-semibold text-sm text-slate-200 tracking-wide">配置中心</span>
                <span className="text-[10px] font-mono text-slate-600 bg-slate-800/60 px-2 py-0.5 rounded-md border border-white/[0.04]">
                  ~/.nanobot/config.json
                </span>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="关闭"
                className="rounded-lg p-1.5 text-slate-500 hover:text-slate-200 hover:bg-white/[0.05] transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Status banner */}
            {status === "error" && errorMsg && (
              <div className="flex items-center gap-2 px-5 py-3 bg-red-500/10 border-b border-red-500/20 shrink-0">
                <AlertCircle size={14} className="text-red-400 shrink-0" />
                <span className="text-xs text-red-300">{errorMsg}</span>
              </div>
            )}
            {status === "success" && (
              <div className="flex items-center gap-2 px-5 py-3 bg-emerald-500/10 border-b border-emerald-500/20 shrink-0">
                <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                <span className="text-xs text-emerald-300">配置已保存</span>
              </div>
            )}

            {/* Editor */}
            <div className="flex-1 min-h-0 overflow-hidden">
              {status === "loading" ? (
                <div className="flex items-center justify-center h-40 text-slate-500 text-sm gap-2">
                  <div className="w-4 h-4 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
                  加载中…
                </div>
              ) : (
                <textarea
                  ref={textareaRef}
                  value={text}
                  onChange={(e) => {
                    setText(e.target.value);
                    setStatus("idle");
                    setErrorMsg("");
                  }}
                  spellCheck={false}
                  className="w-full h-full min-h-[360px] resize-none bg-transparent px-5 py-4 font-mono text-xs text-slate-300 leading-relaxed focus:outline-none placeholder:text-slate-600"
                  placeholder="{}"
                  aria-label="config.json 内容"
                />
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-5 py-3.5 border-t border-white/[0.05] bg-black/30 shrink-0">
              <button
                type="button"
                onClick={handleReset}
                disabled={!isDirty || status === "loading" || status === "saving"}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <RotateCcw size={13} />
                撤销更改
              </button>

              <div className="flex items-center gap-2">
                {isDirty && (
                  <span className="text-[10px] text-amber-500/70 font-medium">未保存的更改</span>
                )}
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={status === "loading" || status === "saving" || !isDirty}
                  className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors shadow-[0_0_15px_rgba(37,99,235,0.3)]"
                >
                  {status === "saving" ? (
                    <>
                      <div className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      保存中…
                    </>
                  ) : (
                    <>
                      <Save size={13} />
                      保存配置
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
