"use client";

import { Send } from "lucide-react";

type Props = {
  value: string;
  disabled?: boolean;
  loading?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export function ChatInput({ value, disabled, loading, onChange, onSubmit }: Props) {
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <input
        className="flex-1 rounded-md bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm outline-none focus:border-zinc-500"
        placeholder="输入消息..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
      <button
        type="submit"
        disabled={disabled}
        className="rounded-md bg-zinc-100 text-zinc-900 px-4 py-2 text-sm font-medium disabled:opacity-40 inline-flex items-center gap-1"
      >
        <Send size={14} />
        {loading ? "发送中" : "发送"}
      </button>
    </form>
  );
}
