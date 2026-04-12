import { NextResponse } from "next/server";
import { listLocalModules } from "@/lib/moduleRegistry";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");

export async function GET() {
  try {
    const upstream = await fetch(`${BACKEND}/api/modules`, { cache: "no-store" });
    if (upstream.ok) {
      const payload = await upstream.json();
      return NextResponse.json(payload);
    }
  } catch {
    // Fall through to local filesystem scan.
  }

  try {
    return NextResponse.json({ items: listLocalModules() });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      { error: { code: "internal_error", message: "Failed to list modules", detail } },
      { status: 500 },
    );
  }
}
