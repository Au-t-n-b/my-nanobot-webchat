"use client";

import { Eye, Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import type { Theme } from "@/hooks/useTheme";

const THEMES: { id: Theme; icon: React.ElementType; label: string; desc: string }[] = [
  { id: "dark",  icon: Moon, label: "深夜", desc: "深夜模式 — 防眩光，暖琥珀调" },
  { id: "light", icon: Sun,  label: "白日", desc: "白日模式 — 高清晰，抗环境光" },
  { id: "soft",  icon: Eye,  label: "护眼", desc: "护眼模式 — 零蓝光，仿纸质阅读" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center gap-1">
      {THEMES.map(({ id, icon: Icon, label, desc }) => (
        <button
          key={id}
          type="button"
          onClick={() => setTheme(id)}
          aria-label={desc}
          title={desc}
          className={
            "inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] transition-colors " +
            (theme === id
              ? "ui-subtle ui-text-primary font-medium"
              : "ui-text-muted hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]")
          }
        >
          <Icon size={11} />
          {label}
        </button>
      ))}
    </div>
  );
}
