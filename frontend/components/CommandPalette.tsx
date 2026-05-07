"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, FolderGit2, Focus, LayoutDashboard, Plus, Settings, Sun, Moon, Trash2, Zap } from "lucide-react";

export type CommandPaletteItem = {
  id: string;
  group: string;
  label: string;
  icon: ReactNode;
  hint?: string;
  shortcut?: string;
  keywords?: string[];
  tone?: "normal" | "accent" | "danger";
  run: () => void;
};

function fuzzyMatch(query: string, hay: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const h = hay.toLowerCase();
  // simple subsequence match: keeps the "fuzzy" feel without heavy deps
  let qi = 0;
  for (let hi = 0; hi < h.length && qi < q.length; hi += 1) {
    if (h[hi] === q[qi]) qi += 1;
  }
  return qi === q.length;
}

/** 全局命令面板：Cmd/Ctrl+K toggle；Esc 关闭（Phase 3：仅前端占位动作） */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const commands = useMemo<CommandPaletteItem[]>(
    () => [
      {
        id: "session:new-survey",
        group: "会话与项目",
        label: "新建勘测会话",
        hint: "清空当前聊天流，回到初始状态",
        shortcut: "↵",
        icon: <Plus size={16} aria-hidden />,
        keywords: ["session", "new", "清空", "重置", "勘测", "会话"],
        run: () => window.dispatchEvent(new Event("nanobot:workbench:clear-chat")),
      },
      {
        id: "session:clear",
        group: "会话与项目",
        label: "清空当前会话",
        hint: "删除当前会话消息（不可撤销）",
        shortcut: "↵",
        icon: <Trash2 size={16} aria-hidden />,
        tone: "danger",
        keywords: ["clear", "session", "danger", "删除", "清空"],
        run: () => window.dispatchEvent(new Event("nanobot:workbench:clear-session")),
      },
      {
        id: "project:switcher",
        group: "会话与项目",
        label: "切换工作区",
        hint: "打开左侧项目/工作区切换面板",
        shortcut: "↵",
        icon: <FolderGit2 size={16} aria-hidden />,
        keywords: ["project", "workspace", "工作区", "项目", "切换"],
        run: () => window.dispatchEvent(new Event("nanobot:workbench:open-project-switcher")),
      },
      {
        id: "view:zen-toggle",
        group: "视图控制",
        label: "切换专注模式 (Zen Mode)",
        hint: "隐藏侧栏与大盘，仅保留会话区",
        shortcut: "↵",
        icon: <Focus size={16} aria-hidden />,
        keywords: ["zen", "focus", "专注", "全屏"],
        run: () => window.dispatchEvent(new Event("nanobot:workbench:toggle-zen")),
      },
      {
        id: "view:dashboard-toggle",
        group: "视图控制",
        label: "展开/收起右侧大盘",
        hint: "切换大盘可见性（若不支持则保持占位）",
        shortcut: "↵",
        icon: <LayoutDashboard size={16} aria-hidden />,
        keywords: ["dashboard", "大盘", "右侧", "toggle"],
        run: () => window.dispatchEvent(new Event("nanobot:workbench:toggle-dashboard")),
      },
      {
        id: "view:theme-dark",
        group: "视图控制",
        label: "切换为深色主题",
        shortcut: "↵",
        icon: <Moon size={16} aria-hidden />,
        keywords: ["theme", "dark", "夜间", "深色"],
        run: () => window.dispatchEvent(new CustomEvent("nanobot:workbench:set-theme", { detail: "dark" })),
      },
      {
        id: "view:theme-light",
        group: "视图控制",
        label: "切换为浅色主题",
        shortcut: "↵",
        icon: <Sun size={16} aria-hidden />,
        keywords: ["theme", "light", "浅色", "白日"],
        run: () => window.dispatchEvent(new CustomEvent("nanobot:workbench:set-theme", { detail: "light" })),
      },
      {
        id: "core:run-skill",
        group: "核心动作",
        label: "运行冷启动分析 (run-skill)",
        hint: "TRIGGER: run-skill",
        shortcut: "↵",
        icon: <Zap size={16} aria-hidden />,
        tone: "accent",
        keywords: ["run-skill", "cold", "analysis", "冷启动", "冷启", "技能"],
        run: () =>
          window.dispatchEvent(
            new CustomEvent("nanobot:workbench:trigger-run-skill", {
              detail: { skill: "cold_start_analysis" },
            }),
          ),
      },
      {
        id: "core:control-center",
        group: "核心动作",
        label: "打开控制中心",
        hint: "模型/Provider/API Key 等设置",
        shortcut: "↵",
        icon: <Settings size={16} aria-hidden />,
        keywords: ["control-center", "config", "设置", "控制中心"],
        run: () => window.dispatchEvent(new Event("nanobot:workbench:open-control-center")),
      },
    ],
    [],
  );

  const filtered = useMemo(() => {
    const s = q.trim();
    if (!s) return commands;
    return commands.filter((c) => {
      const hay = `${c.group} ${c.label} ${c.hint ?? ""} ${(c.keywords ?? []).join(" ")}`;
      return fuzzyMatch(s, hay);
    });
  }, [q, commands]);

  const grouped = useMemo(() => {
    const map = new Map<string, CommandPaletteItem[]>();
    for (const c of filtered) {
      const arr = map.get(c.group) ?? [];
      arr.push(c);
      map.set(c.group, arr);
    }
    return Array.from(map.entries());
  }, [filtered]);

  const flat = filtered;

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActiveIndex(0);
    queueMicrotask(() => inputRef.current?.focus());
  }, [open]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (!open) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => (flat.length ? (i + 1) % flat.length : 0));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => (flat.length ? (i - 1 + flat.length) % flat.length : 0));
        return;
      }
      if (e.key === "Enter") {
        const item = flat[activeIndex];
        if (!item) return;
        e.preventDefault();
        item.run();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, flat, activeIndex]);

  useEffect(() => {
    const onExternalOpen = () => setOpen(true);
    window.addEventListener("nanobot:command-palette:open", onExternalOpen as EventListener);
    return () => window.removeEventListener("nanobot:command-palette:open", onExternalOpen as EventListener);
  }, []);

  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-cmd-index="${activeIndex}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh] backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div
        role="dialog"
        aria-label="命令面板"
        aria-modal="true"
        className="ui-motion w-full max-w-2xl overflow-hidden rounded-2xl bg-[var(--surface-elevated)]/90 shadow-2xl ring-1 ring-white/10 backdrop-blur-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
          <input
            ref={inputRef}
            type="text"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActiveIndex(0);
            }}
            placeholder="输入命令或搜索... (↑↓ 导航，Enter 确认)"
            className="min-w-0 flex-1 bg-transparent text-lg ui-text-primary outline-none placeholder:text-[var(--text-muted)]"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
          />
        </div>
        <div ref={listRef} className="max-h-[min(56vh,420px)] overflow-y-auto py-2" role="listbox">
          {flat.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm ui-text-muted">无匹配命令</div>
          ) : (
            grouped.map(([group, items]) => (
              <div key={group} className="px-2">
                <div className="px-2.5 pb-1.5 pt-2 text-[10px] font-semibold tracking-wider ui-text-muted">
                  {group}
                </div>
                <div className="space-y-1">
                  {items.map((c) => {
                    const idx = flat.findIndex((x) => x.id === c.id);
                    const active = idx === activeIndex;
                    return (
                      <button
                        key={c.id}
                        type="button"
                        data-cmd-index={idx}
                        className={
                          "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm ui-text-primary transition-colors " +
                          (active ? "bg-white/5" : "hover:bg-[var(--surface-3)]")
                        }
                        onMouseEnter={() => setActiveIndex(idx)}
                        onClick={() => {
                          c.run();
                          setOpen(false);
                        }}
                      >
                        <div className="min-w-0 flex items-center gap-2">
                          <span
                            className={
                              "inline-flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] ui-text-muted " +
                              (c.tone === "danger" ? "text-red-400" : c.tone === "accent" ? "text-amber-500" : "")
                            }
                            aria-hidden
                          >
                            {c.icon}
                          </span>
                          <div className="min-w-0">
                            <div className={"truncate " + (c.tone === "danger" ? "text-red-300" : c.tone === "accent" ? "text-amber-400" : "")}>
                              {c.label}
                            </div>
                          {c.hint ? <div className="mt-0.5 truncate text-[11px] ui-text-muted">{c.hint}</div> : null}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {c.shortcut ? <span className="text-[10px] ui-text-muted opacity-70">{c.shortcut}</span> : null}
                          <ChevronRight size={14} className="ui-text-muted opacity-70" aria-hidden />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
