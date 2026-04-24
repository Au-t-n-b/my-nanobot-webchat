"""Scoped Bearer auth middleware for local JSON auth MVP.

MVP strategy (phase C): protect only auth/me, auth/register, and admin/members endpoints.
Other existing AGUI APIs remain anonymous to avoid regressions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiohttp import web

from nanobot.web.local_jwt import verify_token

_PROTECTED_PREFIXES: tuple[str, ...] = (
    "/api/auth/me",
    "/api/auth/register",
    "/api/admin/members",
)


def _bearer_payload(request: web.Request) -> str | None:
    h = (request.headers.get("Authorization") or "").strip()
    if h.lower().startswith("bearer "):
        return h[7:].strip() or None
    return None


@web.middleware
async def local_auth_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse | web.Response]],
) -> web.StreamResponse | web.Response:
    # Let CORS middleware handle OPTIONS first; but be safe here too.
    if request.method == "OPTIONS":
        return await handler(request)

    path = request.path
    if not any(path == p or path.startswith(f"{p}/") for p in _PROTECTED_PREFIXES):
        return await handler(request)

    if path.startswith("/api/auth/login"):
        return await handler(request)

    token = _bearer_payload(request)
    if not token:
        return web.json_response({"detail": "未登录或缺少 Authorization Bearer 令牌"}, status=401)
    try:
        payload = verify_token(token)
    except Exception:
        return web.json_response({"detail": "未登录或令牌已失效"}, status=401)

    request["auth_user"] = payload
    return await handler(request)

