"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light" | "soft";
const STORAGE_KEY = "nanobot_agui_theme";
const DEFAULT: Theme = "dark";

function applyTheme(t: Theme) {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", t);
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(DEFAULT);

  useEffect(() => {
    const stored = (localStorage.getItem(STORAGE_KEY) ?? DEFAULT) as Theme;
    setThemeState(stored);
    applyTheme(stored);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    applyTheme(t);
    localStorage.setItem(STORAGE_KEY, t);
  }, []);

  return { theme, setTheme };
}
