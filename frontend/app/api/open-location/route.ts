/**
 * POST /api/open-location
 * Body: { path: string }
 *
 * Opens the containing folder of the given file path in the OS file manager
 * and selects the file (Windows: Explorer /select; macOS: open -R; Linux: xdg-open).
 *
 * This Next.js API route takes priority over the `/api/:path*` rewrite defined
 * in next.config.ts, so it is served locally without proxying to Python.
 *
 * Python backend equivalent (if running in AGUI_DIRECT mode):
 *   @app.post("/api/open-location")
 *   async def open_location(body: dict):
 *       import os, platform, subprocess
 *       p = os.path.abspath(body.get("path", ""))
 *       if platform.system() == "Windows":
 *           subprocess.Popen(["explorer.exe", f"/select,{p}"])
 *       elif platform.system() == "Darwin":
 *           subprocess.Popen(["open", "-R", p])
 *       else:
 *           subprocess.Popen(["xdg-open", os.path.dirname(p)])
 */

import { exec } from "child_process";
import path from "path";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { path?: unknown };
    const filePath = typeof body.path === "string" ? body.path.trim() : "";

    if (!filePath) {
      return NextResponse.json({ error: "Missing or invalid path" }, { status: 400 });
    }

    const absolutePath = path.resolve(filePath);

    if (process.platform === "win32") {
      // /select highlights the file in Explorer rather than opening it
      exec(`explorer.exe /select,"${absolutePath}"`);
    } else if (process.platform === "darwin") {
      exec(`open -R "${absolutePath}"`);
    } else {
      // Linux: open parent directory
      exec(`xdg-open "${path.dirname(absolutePath)}"`);
    }

    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}
