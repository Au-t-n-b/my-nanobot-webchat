"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";

export type CommandPaletteItem = {
  id: string;
  label: string;
  hint?: string;
  keywords?: string[];
  run: () => void;
};

type Props = {
  open: boolean;
  onClose: () => void;
  commands: CommandPaletteItem[];
};

/** 全局命令面板：Cmd/Ctrl+K；Esc 关闭 */
export function CommandPalette({ open, onClose, commands }: Props) {
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return commands;
    return commands.filter((c) => {
      const hay = `${c.label} ${c.hint ?? ""} ${(c.keywords ?? []).join(" ")}`.toLowerCase();
      return hay.includes(s);
    });
  }, [q, commands]);

  useEffect(() => {
    if (open) {
      setQ("");
      queueMicrotask(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const trap = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", trap, true);
    return () => window.removeEventListener("keydown", trap, true);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/45 px-4 pt-[12vh] backdrop-blur-[3px]"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-label="命令面板"
        aria-modal="true"
        className="w-full max-w-lg rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-[var(--shadow-panel)] overflow-hidden ring-1 ring-black/5 dark:ring-white/10"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
          <Search size={16} className="ui-text-muted shrink-0" aria-hidden />
          <input
            ref={inputRef}
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="输入命令或关键词…"
            className="min-w-0 flex-1 bg-transparent py-1.5 text-sm ui-text-primary outline-none placeholder:text-[var(--text-muted)]"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
          />
          <kbd className="hidden sm:inline rounded border border-[var(--border-subtle)] bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] ui-text-muted">
            Esc
          </kbd>
        </div>
        <ul ref={listRef} className="max-h-[min(50vh,320px)] overflow-y-auto py-1" role="listbox">
          {filtered.length === 0 ? (
            <li className="px-4 py-6 text-center text-sm ui-text-muted">无匹配命令</li>
          ) : (
            filtered.map((c) => (
              <li key={c.id} role="option">
                <button
                  type="button"
                  className="flex w-full flex-col items-start gap-0.5 px-4 py-2.5 text-left text-sm ui-text-primary transition-colors hover:bg-[var(--surface-2)]"
                  onClick={() => {
                    c.run();
                    onClose();
                  }}
                >
                  <span>{c.label}</span>
                  {c.hint ? <span className="text-[11px] ui-text-muted">{c.hint}</span> : null}
                </button>
              </li>
            ))
          )}
        </ul>
        <p className="border-t border-[var(--border-subtle)] px-3 py-2 text-[10px] ui-text-muted">
          提示：Ctrl/⌘ + K 打开；会话内 Ctrl/⌘ + F 仍为消息搜索
        </p>
      </div>
    </div>
  );
}
