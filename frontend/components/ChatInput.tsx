"use client";

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { Send, Square } from "lucide-react";

type Props = {
  disabled?: boolean;
  loading?: boolean;
  onSubmit: (value: string) => void;
  onStop?: () => void;
  focusSignal?: number;
  prefillText?: string;
  /** 输入框上方：提供方 / 模型 等，与 Claude 等主流产品一致在底部切换模型 */
  modelControls?: ReactNode;
  /** 用于与模型条+输入区整体宽度做紧凑布局（如 ModelSelector） */
  inputBarRef?: RefObject<HTMLDivElement | null>;
};

export function ChatInput({
  disabled,
  loading,
  onSubmit,
  onStop,
  focusSignal,
  prefillText,
  modelControls,
  inputBarRef,
}: Props) {
  const [value, setValue] = useState("");
  const trimmed = value.trim();
  const sendActive = trimmed.length > 0 && !loading && !disabled;
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (focusSignal && focusSignal > 0) {
      inputRef.current?.focus();
    }
  }, [focusSignal]);

  useEffect(() => {
    if (typeof prefillText === "string" && prefillText.length > 0) {
      setValue(prefillText);
      inputRef.current?.focus();
    }
  }, [prefillText]);

  const modelGhostRowClass =
    "model-controls-ghost flex min-w-0 flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] bg-transparent px-3 py-2 text-xs dark:border-white/10 " +
    "[&_label]:!m-0 [&_label]:inline-flex [&_label]:min-w-0 [&_label]:max-w-full [&_label]:items-center [&_label]:gap-1.5 " +
    "[&_label]:ui-text-secondary [&_select]:w-40 [&_select]:min-w-0 [&_select]:shrink-0 [&_select]:cursor-pointer [&_select]:rounded-md [&_select]:border-0 " +
    "[&_select]:bg-transparent [&_select]:px-2 [&_select]:py-1 [&_select]:text-[var(--text-secondary)] [&_select]:outline-none " +
    "[&_select]:ring-0 [&_select]:transition-colors " +
    "[&_select:hover]:bg-slate-200/70 dark:[&_select:hover]:bg-white/[0.04] " +
    "[&_select:focus]:bg-slate-200/90 dark:[&_select:focus]:bg-white/[0.06]";

  const fusedShellClass =
    "overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)]/90 shadow-[var(--shadow-card)] transition-shadow " +
    "focus-within:ring-1 focus-within:ring-[color-mix(in_srgb,var(--accent)_28%,transparent)] " +
    "supports-[backdrop-filter]:backdrop-blur-md " +
    "dark:border-white/10 dark:bg-[var(--surface-1)] dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] dark:ring-1 dark:ring-white/[0.08] supports-[backdrop-filter]:dark:backdrop-blur-sm " +
    "dark:focus-within:ring-1 dark:focus-within:ring-[color-mix(in_srgb,var(--accent)_30%,transparent)]";

  const textFieldClass =
    "min-w-0 flex-1 rounded-xl border-0 bg-[var(--surface-2)]/70 px-3 py-2.5 text-base leading-relaxed text-[var(--text-primary)] outline-none " +
    "ring-0 placeholder:text-zinc-400/90 dark:bg-white/[0.03] dark:placeholder:text-zinc-500 dark:focus:bg-white/[0.05] " +
    "focus-visible:ring-0";

  return (
    <div ref={inputBarRef} className="w-full shrink-0">
      <div className={fusedShellClass}>
        {modelControls ? <div className={modelGhostRowClass}>{modelControls}</div> : null}
        <form
          className="flex items-center gap-2 p-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (sendActive) {
              onSubmit(trimmed);
              setValue("");
            }
          }}
        >
          <input
            ref={inputRef}
            className={textFieldClass}
            placeholder="输入消息…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={disabled || loading}
            aria-label="消息输入"
          />
          {loading ? (
            <button
              type="button"
              onClick={() => onStop?.()}
              className={
                "shrink-0 inline-flex items-center gap-2 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-medium text-red-400 ring-1 ring-red-500/25 " +
                "transition-colors hover:bg-red-500/20"
              }
              aria-label="停止生成"
              title="停止生成"
            >
              <Square size={16} aria-hidden />
              停止
            </button>
          ) : (
            <button
              type="submit"
              disabled={!sendActive}
              className="ui-btn-accent shrink-0 rounded-xl p-2.5 disabled:pointer-events-none disabled:opacity-30"
              aria-label="发送"
              title="发送"
            >
              <Send size={17} aria-hidden />
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
