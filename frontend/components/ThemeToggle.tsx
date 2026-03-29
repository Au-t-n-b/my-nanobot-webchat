"use client";

import { Eye, Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import type { Theme } from "@/hooks/useTheme";

const THEMES: { id: Theme; icon: React.ElementType; desc: string }[] = [
  { id: "dark",  icon: Moon, desc: "深夜模式 — 防眩光，暖琥珀调" },
  { id: "light", icon: Sun,  desc: "白日模式 — 高清晰，抗环境光" },
  { id: "soft",  icon: Eye,  desc: "护眼模式 — 零蓝光，仿纸质阅读" },
];

export function ThemeToggle({ vertical = false }: { vertical?: boolean }) {
  const { theme, setTheme } = useTheme();
  return (
    <div className={`flex items-center gap-1 ${vertical ? "flex-col" : "flex-row"}`}>
      {THEMES.map(({ id, icon: Icon, desc }) => (
        <button
          key={id}
          type="button"
          onClick={() => setTheme(id)}
          aria-label={desc}
          title={desc}
          className={
            "inline-flex items-center justify-center rounded-lg p-1.5 transition-colors " +
            (theme === id
              ? "ui-subtle ui-text-primary"
              : "ui-text-muted hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]")
          }
        >
          <Icon size={13} />
        </button>
      ))}
    </div>
  );
}
