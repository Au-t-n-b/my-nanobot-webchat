"use client";

import { useCallback, useEffect, useState } from "react";
import { getLocalStorage } from "@/lib/browserStorage";

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
    const ls = getLocalStorage();
    const stored = (ls?.getItem(STORAGE_KEY) ?? DEFAULT) as Theme;
    setThemeState(stored);
    applyTheme(stored);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    applyTheme(t);
    getLocalStorage()?.setItem(STORAGE_KEY, t);
  }, []);

  return { theme, setTheme };
}
