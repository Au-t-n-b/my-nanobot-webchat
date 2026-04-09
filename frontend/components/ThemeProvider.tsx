"use client";

import { useEffect } from "react";
import { getLocalStorage } from "@/lib/browserStorage";

/** Applies the stored theme on first paint to avoid flash. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const ls = getLocalStorage();
    const stored = ls?.getItem("nanobot_agui_theme") ?? "dark";
    document.documentElement.setAttribute("data-theme", stored);
  }, []);
  return <>{children}</>;
}
