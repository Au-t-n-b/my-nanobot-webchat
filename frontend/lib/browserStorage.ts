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

function isQuotaError(e: unknown): boolean {
  return (
    e instanceof DOMException &&
    (e.name === "QuotaExceededError" || e.code === 22 || e.code === 1014)
  );
}

/** 写入 localStorage；失败（配额、隐私模式等）返回 false。 */
export function safeSetItem(ls: Storage, key: string, value: string): boolean {
  try {
    ls.setItem(key, value);
    return true;
  } catch (e) {
    if (typeof console !== "undefined" && isQuotaError(e)) {
      console.warn("[browserStorage] setItem quota or storage failure", key);
    }
    return false;
  }
}

export function safeRemoveItem(ls: Storage, key: string): boolean {
  try {
    ls.removeItem(key);
    return true;
  } catch {
    return false;
  }
}
