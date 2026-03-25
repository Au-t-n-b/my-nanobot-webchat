"use client";

import { useEffect } from "react";

/** Applies the stored theme on first paint to avoid flash. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const stored = localStorage.getItem("nanobot_agui_theme") ?? "dark";
    document.documentElement.setAttribute("data-theme", stored);
  }, []);
  return <>{children}</>;
}
