"use client";

import { useEffect, useMemo, useRef } from "react";
import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import type { AgentMessage } from "@/hooks/useAgentChat";

type Props = {
  query: string;
  onQueryChange: (q: string) => void;
  onClose: () => void;
  messages: AgentMessage[];
};

export function useSearchMatches(messages: AgentMessage[], query: string) {
  return useMemo(() => {
    if (!query.trim()) return 0;
    const q = query.toLowerCase();
    return messages.reduce((acc, m) => {
      if (!m.content) return acc;
      const text = m.content.toLowerCase();
      let idx = 0;
      let count = 0;
      while ((idx = text.indexOf(q, idx)) !== -1) { count++; idx += q.length; }
      return acc + count;
    }, 0);
  }, [messages, query]);
}

export function SearchOverlay({ query, onQueryChange, onClose, messages }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const total = useSearchMatches(messages, query);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <div
      role="search"
      aria-label="消息搜索"
      className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-2xl ui-panel px-3 py-2 min-w-[280px]"
    >
      <Search size={14} className="ui-text-muted shrink-0" />
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="搜索消息…"
        className="flex-1 bg-transparent text-sm ui-text-primary placeholder:text-[var(--text-muted)] outline-none"
      />
      {query && (
        <span className="text-[11px] ui-text-muted shrink-0 tabular-nums">
          {total} 处
        </span>
      )}
      <div className="flex items-center gap-0.5 shrink-0">
        <button
          type="button"
          aria-label="上一处"
          className="rounded p-1 ui-text-secondary hover:bg-[var(--surface-3)] transition-colors disabled:opacity-30"
          disabled={total === 0}
        >
          <ChevronUp size={14} />
        </button>
        <button
          type="button"
          aria-label="下一处"
          className="rounded p-1 ui-text-secondary hover:bg-[var(--surface-3)] transition-colors disabled:opacity-30"
          disabled={total === 0}
        >
          <ChevronDown size={14} />
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭搜索"
          className="rounded p-1 ui-text-muted hover:bg-[var(--surface-3)] transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
