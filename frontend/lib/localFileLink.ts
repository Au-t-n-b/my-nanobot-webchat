/**
 * If the link should open in the AGUI file preview, return the path string for ``/api/file``.
 * Handles same-origin ``/api/file?path=``, ``file://``, and plain relative/absolute paths without scheme.
 *
 * IMPORTANT: Network URLs (http://, https://) are explicitly excluded to prevent them
 * from being incorrectly treated as local file paths (e.g., 404 errors with garbled paths).
 */
export function extractLocalPreviewPath(href: string | undefined): string | null {
  if (!href || href.startsWith("#")) return null;
  const h = href.trim();

  // Explicitly reject http/https URLs - they must open in new tabs, not file preview
  if (h.startsWith("http://") || h.startsWith("https://")) return null;

  // Reject other known network protocols
  if (h.startsWith("ftp://") || h.startsWith("sftp://") || h.startsWith("ws://") || h.startsWith("wss://")) {
    return null;
  }

  try {
    const base =
      typeof window !== "undefined" && window.location?.origin
        ? window.location.origin
        : "http://127.0.0.1:3000";
    const u = new URL(h, base);
    const pathNoSlash = u.pathname.replace(/\/+$/, "") || "/";
    if (pathNoSlash.endsWith("/api/file") && u.searchParams.has("path")) {
      const p = u.searchParams.get("path");
      // Extra guard: don't return network URLs that somehow ended up as path values
      if (p && p.length > 0 && !p.startsWith("http://") && !p.startsWith("https://")) {
        return p;
      }
      return null;
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

  // Reject any string that looks like a URL scheme (except file:// which was handled above)
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(h)) return null;
  return h;
}
