"use client";

import { useEffect, useRef } from "react";
import { Loader2, Send } from "lucide-react";
import { useState } from "react";

type Props = {
  disabled?: boolean;
  loading?: boolean;
  onSubmit: (value: string) => void;
  focusSignal?: number;
  prefillText?: string;
};

export function ChatInput({ disabled, loading, onSubmit, focusSignal, prefillText }: Props) {
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

  return (
    <form
      className="flex gap-2 items-center rounded-2xl p-1.5 transition-shadow focus-within:ring-1 focus-within:ring-gray-300 dark:focus-within:ring-white/20 focus-within:bg-gray-50/50 dark:focus-within:bg-white/5"
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
        className="ui-input ui-input-focusable flex-1 rounded-xl px-4 py-3 text-base leading-relaxed"
        placeholder="输入消息…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled || loading}
        aria-label="消息输入"
      />
      <button
        type="submit"
        disabled={!sendActive}
        className="ui-btn-accent shrink-0 rounded-xl p-3 disabled:opacity-30 disabled:pointer-events-none transition-colors"
        aria-label={loading ? "发送中" : "发送"}
        title={loading ? "发送中" : "发送"}
      >
        {loading ? <Loader2 size={18} className="animate-spin" aria-hidden /> : <Send size={18} aria-hidden />}
      </button>
    </form>
  );
}
