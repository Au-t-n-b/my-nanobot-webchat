"use client";

import { Loader2, Send } from "lucide-react";

type Props = {
  value: string;
  disabled?: boolean;
  loading?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export function ChatInput({ value, disabled, loading, onChange, onSubmit }: Props) {
  const trimmed = value.trim();
  const sendActive = trimmed.length > 0 && !loading && !disabled;

  return (
    <form
      className="flex gap-2 items-center"
      onSubmit={(e) => {
        e.preventDefault();
        if (sendActive) onSubmit();
      }}
    >
      <input
        className="ui-input ui-input-focusable flex-1 rounded-xl px-3 py-2.5 text-sm"
        placeholder="输入消息…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || loading}
        aria-label="消息输入"
      />
      <button
        type="submit"
        disabled={!sendActive}
        className="ui-btn-accent shrink-0 rounded-xl p-2.5 disabled:opacity-30 disabled:pointer-events-none transition-colors"
        aria-label={loading ? "发送中" : "发送"}
        title={loading ? "发送中" : "发送"}
      >
        {loading ? <Loader2 size={18} className="animate-spin" aria-hidden /> : <Send size={18} aria-hidden />}
      </button>
    </form>
  );
}
