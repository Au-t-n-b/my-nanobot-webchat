/**
 * Build a WebSocket URL for the remote browser endpoint.
 *
 * Handles both http → ws and https → wss so the app works correctly in
 * TLS-terminated production environments (secure pages may not open ws://).
 *
 * @param filePath         The preview path, e.g. "browser://https://example.com"
 * @param containerWidth   CSS pixel width of the display container.
 * @param containerHeight  CSS pixel height of the display container.
 *                         When both are provided the backend renders at exactly
 *                         this aspect ratio (×2 DPR for crispness), eliminating
 *                         all black bars in the object-contain view.
 */
export function buildBrowserWsUrl(
  filePath: string,
  containerWidth?: number,
  containerHeight?: number,
): string {
  const initialUrl = filePath.replace(/^browser:\/\//, "");

  const apiBase = (
    process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765"
  ).replace(/\/$/, "");

  const wsBase = apiBase.startsWith("https://")
    ? apiBase.replace("https://", "wss://")
    : apiBase.replace("http://", "ws://");

  const params = new URLSearchParams({ url: initialUrl });
  if (containerWidth && containerWidth > 0) {
    params.set("vw", String(Math.round(containerWidth)));
  }
  if (containerHeight && containerHeight > 0) {
    params.set("vh", String(Math.round(containerHeight)));
  }
  return `${wsBase}/api/browser?${params.toString()}`;
}
