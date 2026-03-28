/**
 * POST /api/chat  — SSE streaming proxy
 *
 * Next.js `rewrites()` buffers the entire upstream body before forwarding it
 * to the browser, which breaks Server-Sent Events: the browser never receives
 * any bytes until the run finishes (or the 20-second idle-timeout fires).
 *
 * This API Route takes priority over the `/api/:path*` rewrite and manually
 * pipes the upstream ReadableStream straight to the browser with no buffering.
 */

import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
// Use the Node.js runtime so we get native streaming support.
export const runtime = "nodejs";

const BACKEND = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765"
).replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      // Node 18+ fetch requires this for streaming request bodies.
      // @ts-expect-error  duplex is not yet in the TS lib types
      duplex: "half",
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Backend unreachable: ${String(err)}` },
      { status: 502 },
    );
  }

  if (!upstream.body) {
    return NextResponse.json({ detail: "No response body from backend" }, { status: 502 });
  }

  // Pipe the raw SSE stream to the browser.
  // Setting these headers tells every layer (Next.js, proxies, CDNs) not to buffer.
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",   // disables nginx buffering
      "Connection": "keep-alive",
      "Transfer-Encoding": "chunked",
    },
  });
}

// OPTIONS preflight for CORS (matches the Python backend's CORS handling)
export async function OPTIONS() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
