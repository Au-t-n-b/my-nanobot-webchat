/** Build ``GET /api/file`` URL for Nanobot AGUI (path as raw path string, UTF-8). */
export function buildFileUrl(apiBase: string, path: string): string {
  const base = apiBase.replace(/\/$/, "");
  return `${base}/api/file?path=${encodeURIComponent(path)}`;
}
