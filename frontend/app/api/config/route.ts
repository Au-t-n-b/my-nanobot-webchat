/**
 * GET  /api/config  — 读取 ~/.nanobot/config.json，敏感字段替换为 ******
 * POST /api/config  — 接收前端配置写入文件，****** 字段保持原值不覆盖
 */

import fs from "fs";
import path from "path";
import os from "os";
import { NextResponse } from "next/server";

const CONFIG_PATH = path.join(os.homedir(), ".nanobot", "config.json");

const SENSITIVE_PATTERNS = ["password", "apikey", "api_key", "token", "secret", "passwd"];

function isSensitive(key: string): boolean {
  const lower = key.toLowerCase();
  return SENSITIVE_PATTERNS.some((p) => lower.includes(p));
}

type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];
type JsonObject = { [key: string]: JsonValue };

function maskObject(obj: JsonObject): JsonObject {
  const out: JsonObject = {};
  for (const [k, v] of Object.entries(obj)) {
    if (isSensitive(k) && typeof v === "string" && v !== "") {
      out[k] = "******";
    } else if (v !== null && typeof v === "object" && !Array.isArray(v)) {
      out[k] = maskObject(v as JsonObject);
    } else {
      out[k] = v;
    }
  }
  return out;
}

function mergeWithOriginal(incoming: JsonObject, original: JsonObject): JsonObject {
  const out: JsonObject = { ...original };
  for (const [k, v] of Object.entries(incoming)) {
    if (isSensitive(k) && v === "******") {
      // keep existing value — do not overwrite with placeholder
    } else if (
      v !== null &&
      typeof v === "object" &&
      !Array.isArray(v) &&
      original[k] !== null &&
      typeof original[k] === "object" &&
      !Array.isArray(original[k])
    ) {
      out[k] = mergeWithOriginal(v as JsonObject, original[k] as JsonObject);
    } else {
      out[k] = v;
    }
  }
  return out;
}

function readConfig(): JsonObject {
  if (!fs.existsSync(CONFIG_PATH)) return {};
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8")) as JsonObject;
  } catch {
    return {};
  }
}

export async function GET() {
  try {
    const config = readConfig();
    return NextResponse.json(maskObject(config));
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(req: Request) {
  try {
    const incoming = (await req.json()) as JsonObject;
    const existing = readConfig();
    const merged = mergeWithOriginal(incoming, existing);

    const dir = path.dirname(CONFIG_PATH);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(merged, null, 2), "utf-8");
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
