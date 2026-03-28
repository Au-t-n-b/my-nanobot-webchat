"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Globe, Loader2, RefreshCw, WifiOff } from "lucide-react";
import { buildBrowserWsUrl } from "@/lib/browserWsUrl";

type ConnectionStatus = "connecting" | "connected" | "error" | "closed";

type Props = {
  /** Full preview path, e.g. "browser://https://example.com" */
  filePath: string;
};

/**
 * Decode JPEG base64 and blit to canvas. Prefer createImageBitmap (often
 * offloads decode); fall back to Image for older engines.
 */
async function paintJpegBase64ToCanvas(
  canvas: HTMLCanvasElement,
  b64: string,
): Promise<void> {
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) return;
  try {
    const blob = await fetch(`data:image/jpeg;base64,${b64}`).then((r) => r.blob());
    const bmp = await createImageBitmap(blob);
    try {
      ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    } finally {
      bmp.close();
    }
  } catch {
    await new Promise<void>((resolve, reject) => {
      const img = new window.Image();
      img.onload = () => {
        try {
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          resolve();
        } catch (e) {
          reject(e);
        }
      };
      img.onerror = () => reject(new Error("image decode failed"));
      img.src = `data:image/jpeg;base64,${b64}`;
    });
  }
}

export function RemoteBrowser({ filePath }: Props) {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [hasFrame, setHasFrame] = useState(false);
  const [currentUrl, setCurrentUrl] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // True for ~300 ms after each new frame arrives — drives the live-pulse dot
  const [isLive, setIsLive] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imeInputRef = useRef<HTMLInputElement>(null);
  const livePulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Must match backend device_scale_factor=2 for crisp text.
  const renderDprRef = useRef(2);

  // IME state: block individual key events while composing (e.g. Chinese pinyin)
  const isComposingRef = useRef(false);

  // Wheel coalescing: accumulate deltas and send at ~16fps
  const accumulatedScrollRef = useRef({ deltaX: 0, deltaY: 0 });
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Latest JPEG base64 waiting for paint — coalesced to one draw per animation frame */
  const pendingFrameB64Ref = useRef<string | null>(null);
  const rafPaintScheduledRef = useRef(false);
  const lastUrlForCompareRef = useRef<string | null>(null);
  const lastLiveIndicatorAtRef = useRef(0);
  const hasFramePaintedRef = useRef(false);

  // ── WebSocket lifecycle ──────────────────────────────────────────────────

  useEffect(() => {
    // React 18 Strict Mode double-invoke defence:
    //   Mount → cleanup (phantom) → Mount (real)
    // setTimeout(fn, 0) defers WS creation past the phantom cycle.
    let isMounted = true;
    let ws: WebSocket | null = null;

    setStatus("connecting");
    setHasFrame(false);
    setCurrentUrl("");
    setErrorMsg(null);
    setIsLive(false);
    pendingFrameB64Ref.current = null;
    rafPaintScheduledRef.current = false;
    lastUrlForCompareRef.current = null;
    lastLiveIndicatorAtRef.current = 0;
    hasFramePaintedRef.current = false;

    // Clear canvas on reconnect
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx?.clearRect(0, 0, canvas.width, canvas.height);
    }

    const schedulePaint = () => {
      if (rafPaintScheduledRef.current) return;
      rafPaintScheduledRef.current = true;
      requestAnimationFrame(() => {
        rafPaintScheduledRef.current = false;
        const b64 = pendingFrameB64Ref.current;
        pendingFrameB64Ref.current = null;
        if (!b64 || !isMounted) return;
        const cvs = canvasRef.current;
        if (!cvs) return;
        void paintJpegBase64ToCanvas(cvs, b64)
          .then(() => {
            if (pendingFrameB64Ref.current) schedulePaint();
          })
          .catch(() => {
            if (pendingFrameB64Ref.current) schedulePaint();
          });
      });
    };

    const timer = setTimeout(() => {
      if (!isMounted) return;

      const el = containerRef.current;
      const containerWidth  = el?.clientWidth  ?? 0;
      const containerHeight = el?.clientHeight ?? 0;

      // Size the canvas to the container so drawImage fills with zero black bars
      const cvs = canvasRef.current;
      if (cvs && containerWidth > 0 && containerHeight > 0) {
        const dpr = renderDprRef.current;
        // Internal backing store at 2× for crisp rendering, CSS stays 1×.
        cvs.width  = Math.max(1, Math.round(containerWidth * dpr));
        cvs.height = Math.max(1, Math.round(containerHeight * dpr));
      }

      const wsUrl = buildBrowserWsUrl(
        filePath,
        containerWidth  || undefined,
        containerHeight || undefined,
      );

      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isMounted) setStatus("connected");
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const msg = JSON.parse(event.data as string) as {
            type: string;
            data?: string;
            url?: string;
            message?: string;
          };

          if (msg.type === "frame") {
            if (msg.data) {
              // Queue latest frame — at most one rAF worth of work per screen refresh
              pendingFrameB64Ref.current = msg.data;
              schedulePaint();

              if (!hasFramePaintedRef.current) {
                hasFramePaintedRef.current = true;
                setHasFrame(true);
              }

              // Throttle live-dot React updates (was every frame → main-thread jank)
              const now = Date.now();
              if (now - lastLiveIndicatorAtRef.current > 450) {
                lastLiveIndicatorAtRef.current = now;
                if (livePulseTimer.current) clearTimeout(livePulseTimer.current);
                setIsLive(true);
                livePulseTimer.current = setTimeout(() => setIsLive(false), 280);
              }
            }
            // Backend only sends url when it changes — cheap setState
            if (msg.url !== undefined && msg.url !== lastUrlForCompareRef.current) {
              lastUrlForCompareRef.current = msg.url;
              setCurrentUrl(msg.url);
            }
          } else if (msg.type === "error") {
            setErrorMsg(msg.message ?? "Unknown error");
            setStatus("error");
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        if (isMounted) {
          setStatus("error");
          setErrorMsg("WebSocket connection failed");
        }
      };

      ws.onclose = () => {
        if (isMounted) setStatus((prev) => (prev === "error" ? prev : "closed"));
      };
    }, 0);

    return () => {
      isMounted = false;
      clearTimeout(timer);
      if (livePulseTimer.current) clearTimeout(livePulseTimer.current);
      if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
        ws.close();
      }
      wsRef.current = null;
    };
  }, [filePath]);

  // ── Interaction helpers ──────────────────────────────────────────────────

  const sendAction = useCallback((payload: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  /**
   * Canvas click → (x_percent, y_percent) in [0,1]².
   *
   * The canvas fills the container at the same aspect ratio as the remote
   * viewport (both set to container dimensions at connect time), so click
   * coordinates map directly — no letterbox compensation needed.
   */
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (status !== "connected") return;
      const rect = e.currentTarget.getBoundingClientRect();
      sendAction({
        action: "browser_interaction",
        type: "click",
        x_percent: (e.clientX - rect.left) / rect.width,
        y_percent: (e.clientY - rect.top)  / rect.height,
      });
    },
    [status, sendAction],
  );

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      if (status !== "connected") return;
      e.preventDefault();
      accumulatedScrollRef.current.deltaX += e.deltaX;
      accumulatedScrollRef.current.deltaY += e.deltaY;

      if (scrollTimerRef.current) return;
      scrollTimerRef.current = setTimeout(() => {
        scrollTimerRef.current = null;
        const { deltaX, deltaY } = accumulatedScrollRef.current;
        accumulatedScrollRef.current = { deltaX: 0, deltaY: 0 };
        if (deltaX === 0 && deltaY === 0) return;
        sendAction({
          action: "browser_interaction",
          type: "scroll",
          delta_x: deltaX,
          delta_y: deltaY,
          // Back-compat for older backends
          deltaY: deltaY,
        });
      }, 60);
    },
    [status, sendAction],
  );

  const focusImeProxy = useCallback(() => {
    if (status !== "connected") return;
    const el = imeInputRef.current;
    if (!el) return;
    // Avoid scrolling jumps on focus
    el.focus({ preventScroll: true });
  }, [status]);

  const handleImeBlur = useCallback(() => {
    // Keep focus captured so OS IME stays available while interacting with the canvas.
    // Use a timer to avoid fighting with unmount / state transitions.
    if (status !== "connected") return;
    setTimeout(() => focusImeProxy(), 0);
  }, [focusImeProxy, status]);

  const handleImeCompositionStart = useCallback(() => {
    isComposingRef.current = true;
  }, []);

  const handleImeCompositionEnd = useCallback(
    (e: React.CompositionEvent<HTMLInputElement>) => {
      isComposingRef.current = false;
      if (status !== "connected") return;
      // Some IMEs may provide the committed string via value instead of data
      const text = (e.data ?? "") || e.currentTarget.value || "";
      if (text) {
        sendAction({ action: "browser_interaction", type: "insert_text", text });
      }
      // Clear proxy field to avoid accumulating characters
      e.currentTarget.value = "";
    },
    [sendAction, status],
  );

  const handleImeKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (status !== "connected") return;

      // If IME is composing, do NOT forward partial pinyin keystrokes.
      // Also ignore the special Process key.
      if ((e.nativeEvent as KeyboardEvent).isComposing || e.key === "Process") {
        return;
      }

      // Prevent host page from handling keys; always proxy to remote.
      e.preventDefault();

      // Enter: force hard submit
      if (e.key === "Enter") {
        sendAction({ action: "browser_interaction", type: "keyboard", key: "Enter" });
      } else {
        // All other printable keys (letters/numbers/symbols) and special keys
        // are forwarded as physical key presses.
        sendAction({
          action: "browser_interaction",
          type: "keyboard",
          key: e.key,
          shift: e.shiftKey,
          ctrl: e.ctrlKey,
          alt: e.altKey,
        });
      }

      // Keep proxy field empty
      e.currentTarget.value = "";
    },
    [sendAction, status],
  );

  const handleImeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    // If not composing, clear immediately so the proxy input never accumulates visible text.
    // While composing, do NOT clear here (it can break IME commit on some browsers).
    const ne = e.nativeEvent as InputEvent & { isComposing?: boolean };
    if (ne?.isComposing) return;
    e.currentTarget.value = "";
  }, []);

  /**
   * Keyboard handler — skipped entirely while an IME composition is active.
   *
   * When the user is typing Chinese/Japanese/Korean through the system IME,
   * individual keystrokes (e.g. pinyin letters) must NOT be forwarded because:
   *  a) they would type raw Latin characters into the remote page, and
   *  b) the composition result is already sent via onCompositionEnd.
   *
   * Enter is explicitly prevented at the host-browser level so it does not
   * submit a form or navigate the host page; it is still forwarded to the
   * remote Playwright page where it triggers the intended action.
   */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (status !== "connected") return;

      // IME composing / Process key: do NOT forward partial pinyin keystrokes
      // (or we'll type raw Latin letters into the remote input).
      if (isComposingRef.current || e.key === "Process") return;

      // Prevent the host browser from acting on structural keys while still
      // forwarding them to the remote page
      if (["Tab", "Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " "].includes(e.key)) {
        e.preventDefault();
      }

      // Force hard Enter so SPA search boxes submit reliably
      if (e.key === "Enter") {
        sendAction({ action: "browser_interaction", type: "keyboard", key: "Enter" });
        return;
      }

      sendAction({
        action: "browser_interaction",
        type: "keyboard",
        key: e.key,
        shift: e.shiftKey,
        ctrl: e.ctrlKey,
        alt: e.altKey,
      });
    },
    [status, sendAction],
  );

  const handleRefresh = useCallback(() => {
    sendAction({ action: "browser_interaction", type: "refresh" });
  }, [sendAction]);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full min-h-0 gap-2">

      {/* ── Frosted-glass address bar ── */}
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs shrink-0 border"
        style={{
          background: "rgba(255,255,255,0.06)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          borderColor: "rgba(255,255,255,0.10)",
        }}
      >
        {/* Favicon / live indicator */}
        <div className="relative shrink-0">
          <Globe size={12} className="text-zinc-400" />
          {isLive && (
            <span
              className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--success, #22c55e)", animation: "ping 0.6s ease-out" }}
            />
          )}
        </div>

        {/* URL text */}
        <span
          className="flex-1 truncate font-mono text-[11px] select-all"
          style={{ color: "var(--text-secondary, #a1a1aa)" }}
          title={currentUrl || undefined}
        >
          {currentUrl || (status === "connecting" ? "connecting…" : "—")}
        </span>

        {/* Refresh button */}
        <button
          type="button"
          onClick={handleRefresh}
          disabled={status !== "connected"}
          title="刷新页面"
          aria-label="刷新页面"
          className="shrink-0 rounded-md p-1 transition-colors disabled:opacity-40"
          style={{ color: "var(--text-secondary)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.08)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <RefreshCw size={11} />
        </button>
      </div>

      {/* ── Viewport ── */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-0 rounded-xl overflow-hidden"
        style={{ background: "var(--surface-1, #111)" }}
        onMouseDownCapture={focusImeProxy}
        onTouchStartCapture={focusImeProxy}
        onWheel={handleWheel}
      >
        {/*
          <canvas> fills the container completely.
          Its internal .width/.height are set to containerWidth × containerHeight
          at connect time (same dimensions sent to the backend), so drawImage()
          maps the JPEG pixel-perfectly with no black bars or stretching.
          tabIndex / onKeyDown are on the canvas itself so it receives focus and
          captures keyboard events without a wrapper div intercept.
        */}
        <canvas
          ref={canvasRef}
          className="block w-full h-full outline-none"
          style={{ cursor: status === "connected" ? "crosshair" : "default" }}
          tabIndex={-1}
          onClick={handleCanvasClick}
          onKeyDown={handleKeyDown}
        />

        {/* IME proxy input: focusable but visually hidden (NOT display:none) */}
        <input
          ref={imeInputRef}
          type="text"
          inputMode="text"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          className="absolute top-0 left-0 opacity-0 w-1 h-1 pointer-events-none"
          tabIndex={-1}
          onBlur={handleImeBlur}
          onCompositionStart={handleImeCompositionStart}
          onCompositionEnd={handleImeCompositionEnd}
          onKeyDown={handleImeKeyDown}
          onChange={handleImeChange}
        />

        {/* Non-connected state overlay */}
        {status !== "connected" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80 text-white">
            {status === "connecting" && (
              <>
                <Loader2 size={28} className="animate-spin text-zinc-400" />
                <p className="text-sm text-zinc-400">正在连接浏览器…</p>
              </>
            )}
            {status === "error" && (
              <>
                <WifiOff size={28} className="text-red-400" />
                <p className="text-sm text-red-300 text-center px-4 max-w-xs leading-relaxed">
                  {errorMsg ?? "连接失败"}
                </p>
                {(errorMsg?.includes("playwright") || errorMsg?.includes("Chromium")) && (
                  <code className="text-xs text-zinc-400 bg-zinc-900/80 rounded-lg px-3 py-1.5 mt-1 border border-zinc-700">
                    python -m playwright install chromium
                  </code>
                )}
              </>
            )}
            {status === "closed" && (
              <>
                <WifiOff size={28} className="text-zinc-500" />
                <p className="text-sm text-zinc-400">连接已关闭</p>
              </>
            )}
          </div>
        )}

        {/* Connected but no frame painted yet */}
        {status === "connected" && !hasFrame && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 size={22} className="animate-spin text-zinc-500" />
          </div>
        )}
      </div>
    </div>
  );
}
