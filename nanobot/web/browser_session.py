"""Playwright-backed remote browser session for AGUI WebSocket streaming."""

from __future__ import annotations

import asyncio
import random
import base64
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright

# Default viewport used when the client does not supply a container width.
_DEFAULT_VIEWPORT_W = 1280
_DEFAULT_VIEWPORT_H = 800

FRAME_INTERVAL = 1.0 / 12       # 12 FPS normal rate
FRAME_INTERVAL_IDLE = 1.0 / 3  # 3 FPS when page is static (6 consecutive identical frames)
IDLE_THRESHOLD = 6              # consecutive unchanged frames before throttling

# Global browser singleton – created once, shared across sessions via new_context().
_playwright_instance: Playwright | None = None
_browser_instance: Browser | None = None
_browser_lock = asyncio.Lock()

# Keys that require keyboard.press() rather than keyboard.type()
_SPECIAL_KEYS = {
    "Enter", "Backspace", "Delete", "Tab", "Escape",
    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "Home", "End", "PageUp", "PageDown",
    "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "F9", "F10", "F11", "F12",
    "Control", "Alt", "Shift", "Meta",
    "Insert", "CapsLock",
}


async def _get_browser() -> Browser:
    """Return (or lazily create) the global Playwright browser instance."""
    global _playwright_instance, _browser_instance  # noqa: PLW0603

    async with _browser_lock:
        if _browser_instance is not None and _browser_instance.is_connected():
            return _browser_instance

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. "
                "Run: pip install 'nanobot-ai[browser]' && playwright install chromium"
            ) from exc

        try:
            _playwright_instance = await async_playwright().start()
            _browser_instance = await _playwright_instance.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to launch Chromium: {exc}. "
                "Try running: playwright install chromium"
            ) from exc
        return _browser_instance


def _compute_viewport(
    container_width: int | None,
    container_height: int | None = None,
) -> tuple[int, int]:
    """Return (width, height) for the Playwright context viewport.

    Renders at 2× DPR so text stays crisp at the display resolution.

    When BOTH container_width and container_height are supplied the viewport
    matches the container's exact aspect ratio → object-contain fills with
    zero black bars.  When only width is given, height is derived from the
    default 1280×800 ratio.
    """
    if container_width and container_width > 0:
        w = container_width * 2  # 2× DPR
        if container_height and container_height > 0:
            h = container_height * 2
        else:
            h = int(w * _DEFAULT_VIEWPORT_H / _DEFAULT_VIEWPORT_W)
        return w, h
    return _DEFAULT_VIEWPORT_W, _DEFAULT_VIEWPORT_H


class BrowserSession:
    """One isolated Playwright context + page per WebSocket connection.

    Each session gets its own BrowserContext so Cookie, LocalStorage, and
    cache are fully isolated – closing the session destroys all traces.
    """

    def __init__(
        self,
        container_width: int | None = None,
        container_height: int | None = None,
    ) -> None:
        vw, vh = _compute_viewport(container_width, container_height)
        self._viewport_w = vw
        self._viewport_h = vh
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._last_frame_hash: str = ""

    async def start(self, initial_url: str) -> None:
        """Launch a fresh isolated context and navigate to *initial_url*."""
        browser = await _get_browser()
        self._context = await browser.new_context(
            viewport={"width": self._viewport_w, "height": self._viewport_h},
            device_scale_factor=2,
            ignore_https_errors=True,
        )
        self._page = await self._context.new_page()
        try:
            await self._page.goto(initial_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass

    async def screenshot_b64_if_changed(self) -> str | None:
        """Capture a JPEG screenshot; return base64 string or None if unchanged.

        Returns None (instead of raising) when the page is navigating, closing,
        or in a transient CDP error state so the frame loop stays alive.
        """
        if self._page is None or self._page.is_closed():
            return None
        try:
            from playwright.async_api import Error as _PWError
            # quality 52: good visual / smaller payload → smoother WS + decode
            data = await self._page.screenshot(type="jpeg", quality=52)
        except Exception as exc:
            err = str(exc)
            # Navigation/transition/close errors → skip frame silently
            if any(kw in err for kw in (
                "Unable to capture screenshot",
                "Target closed",
                "has been closed",
                "Session closed",
                "Target page",
                "Execution context",
            )):
                return None
            raise
        h = hashlib.md5(data).hexdigest()  # noqa: S324 – non-cryptographic use
        if h == self._last_frame_hash:
            return None
        self._last_frame_hash = h
        return base64.b64encode(data).decode()

    @property
    def current_url(self) -> str:
        if self._page is None:
            return ""
        return self._page.url

    @property
    def viewport_ratio(self) -> float:
        return self._viewport_w / self._viewport_h

    async def click(self, x_percent: float, y_percent: float) -> None:
        """Click at a position expressed as fractions of the viewport."""
        if self._page is None:
            return
        x = self._viewport_w * max(0.0, min(1.0, x_percent))
        y = self._viewport_h * max(0.0, min(1.0, y_percent))
        # Humanize: small jitter + stepped move + click(delay)
        # NOTE: use mouse.click so the page receives a real 'click' event
        # (mousedown/mouseup alone may not focus inputs or trigger SPA handlers).
        jx = x + random.uniform(-1.2, 1.2)
        jy = y + random.uniform(-1.2, 1.2)
        await self._page.mouse.move(jx, jy, steps=10)
        await self._page.mouse.click(jx, jy, delay=int(random.uniform(90, 150)))

    async def scroll(self, delta_x: float = 0.0, delta_y: float = 0.0) -> None:
        """Scroll the page by (delta_x, delta_y) pixels."""
        if self._page is None:
            return
        await self._page.mouse.wheel(delta_x, delta_y)

    async def keyboard_input(
        self,
        key: str,
        ctrl: bool = False,
        shift: bool = False,
        alt: bool = False,
    ) -> None:
        """Send a key event to the page.

        When modifier keys are active, a Playwright combo string is built:
        e.g. ctrl+shift+"a" → "Control+Shift+a".
        Plain printable characters use keyboard.type(); special keys and
        combos use keyboard.press().
        """
        if self._page is None:
            return

        # Hard Enter is critical for SPA form submits/search boxes.
        if key == "Enter":
            await self._page.keyboard.press("Enter")
            return

        has_modifier = ctrl or shift or alt
        if has_modifier:
            parts: list[str] = []
            if ctrl:
                parts.append("Control")
            if alt:
                parts.append("Alt")
            if shift:
                parts.append("Shift")
            # For printable chars with modifiers, pass lowercase base key
            base = key if key in _SPECIAL_KEYS else (key.lower() if len(key) == 1 else key)
            parts.append(base)
            await self._page.keyboard.press("+".join(parts))
        elif key in _SPECIAL_KEYS:
            await self._page.keyboard.press(key)
        elif len(key) == 1:
            await self._page.keyboard.type(key)
        # Ignore unrecognised multi-char strings (e.g. "Dead", "Unidentified")

    async def insert_text(self, text: str) -> None:
        """Insert a composed text string directly (used for IME / CJK input).

        Unlike keyboard.type() which simulates individual key events,
        insert_text bypasses the key event pipeline and inserts the Unicode
        string directly into the focused element — the correct approach for
        multi-character IME compositions such as Chinese pinyin.
        """
        if self._page is None or not text:
            return
        await self._page.keyboard.insert_text(text)

    async def reload(self) -> None:
        """Reload the current page."""
        if self._page is None:
            return
        try:
            await self._page.reload(wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass

    async def close(self) -> None:
        """Destroy the context, wiping all session data."""
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
