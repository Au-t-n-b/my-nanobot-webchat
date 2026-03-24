/**
 * If the link should open in the AGUI file preview, return the path string for ``/api/file``.
 * Handles same-origin ``/api/file?path=``, ``file://``, and plain relative/absolute paths without scheme.
 */
export function extractLocalPreviewPath(href: string | undefined): string | null {
  if (!href || href.startsWith("#")) return null;
  const h = href.trim();

  try {
    const base =
      typeof window !== "undefined" && window.location?.origin
        ? window.location.origin
        : "http://127.0.0.1:3000";
    const u = new URL(h, base);
    const pathNoSlash = u.pathname.replace(/\/+$/, "") || "/";
    if (pathNoSlash.endsWith("/api/file") && u.searchParams.has("path")) {
      const p = u.searchParams.get("path");
      return p && p.length > 0 ? p : null;
    }
  } catch {
    /* continue */
  }

  if (h.startsWith("file:")) {
    try {
      const u = new URL(h);
      let p = u.pathname;
      if (p.startsWith("/") && /^\/[A-Za-z]:/.test(p)) p = p.slice(1);
      return decodeURIComponent(p);
    } catch {
      return null;
    }
  }

  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(h)) return null;
  return h;
}
