/** Build absolute ``GET /api/file`` URL on the Python AGUI host. */
export function buildFileUrl(apiBase: string, path: string): string {
  const base = apiBase.replace(/\/$/, "");
  return `${base}/api/file?path=${encodeURIComponent(path)}`;
}

/**
 * Same-origin URL for file preview (Next.js rewrites proxy to AGUI).
 * Use in ``href``, ``<img src>``, ``<iframe src>``, and ``fetch`` from the browser.
 */
export function buildProxiedFileUrl(path: string): string {
  return `/api/file?path=${encodeURIComponent(path)}`;
}

/**
 * Construct an action API URL, respecting the AGUI_DIRECT env setting.
 * When NEXT_PUBLIC_AGUI_DIRECT=1, points directly at the Python host.
 * Otherwise uses same-origin path (Next.js rewrites proxy to AGUI).
 */
export function apiActionUrl(path: string): string {
  if (process.env.NEXT_PUBLIC_AGUI_DIRECT === "1") {
    const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${base}${p}`;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

/**
 * Open the containing folder of `path` in the OS file manager.
 *
 * Requires a Python backend endpoint:
 *   POST /api/open-location  { "path": "<absolute-path>" }
 *
 * Python implementation (bridge/routes.py or similar):
 *   import os, platform, subprocess
 *   @app.post("/api/open-location")
 *   async def open_location(body: dict):
 *       path = body.get("path", "")
 *       if platform.system() == "Windows":
 *           subprocess.Popen(["explorer", "/select,", os.path.abspath(path)])
 *       elif platform.system() == "Darwin":
 *           subprocess.Popen(["open", "-R", os.path.abspath(path)])
 *       else:
 *           subprocess.Popen(["xdg-open", os.path.dirname(os.path.abspath(path))])
 */
export async function openLocation(path: string): Promise<void> {
  await fetch(apiActionUrl("/api/open-location"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}
