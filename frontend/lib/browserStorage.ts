/**
 * Safe access to `localStorage` for SSR, non-browser runtimes, and broken
 * Node/polyfill globals (e.g. incomplete Web Storage) where `getItem` may not
 * be a function.
 */
export function getLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    const ls = window.localStorage;
    if (
      ls != null &&
      typeof ls.getItem === "function" &&
      typeof ls.setItem === "function" &&
      typeof ls.removeItem === "function"
    ) {
      return ls;
    }
  } catch {
    // Quota, privacy mode, or access denied
  }
  return null;
}
