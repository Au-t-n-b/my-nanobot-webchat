import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { BridgeRootConfigShape } from "./bridge-config.js";
import { defaultBridgeSdk, defaultInternalChat } from "./bridge-config.js";

export function defaultConfigPath(): string {
  const fromEnv = process.env.NANOBOT_CONFIG_PATH?.trim();
  if (fromEnv) return fromEnv;
  return join(homedir(), ".nanobot", "config.json");
}

export function loadBridgeRootConfig(path?: string): BridgeRootConfigShape {
  const p = path ?? defaultConfigPath();
  if (!existsSync(p)) {
    return {
      bridge_sdk: { ...defaultBridgeSdk },
      internal_chat: { ...defaultInternalChat },
    };
  }
  try {
    const raw = readFileSync(p, "utf-8");
    const data = JSON.parse(raw) as BridgeRootConfigShape;
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

function pick<T extends Record<string, unknown>>(obj: unknown, snake: string, camel: string): T | undefined {
  if (!obj || typeof obj !== "object") return undefined;
  const o = obj as Record<string, unknown>;
  const v = o[snake] ?? o[camel];
  return v && typeof v === "object" ? (v as T) : undefined;
}

export function mergeInternalChat(cfg: BridgeRootConfigShape): import("./bridge-config.js").InternalChatConfigShape {
  const partial = pick<Partial<import("./bridge-config.js").InternalChatConfigShape>>(
    cfg,
    "internal_chat",
    "internalChat",
  );
  return { ...defaultInternalChat, ...(partial ?? {}) };
}

export function mergeBridgeSdk(cfg: BridgeRootConfigShape): import("./bridge-config.js").BridgeSdkConfigShape {
  const partial = pick<Partial<import("./bridge-config.js").BridgeSdkConfigShape>>(cfg, "bridge_sdk", "bridgeSdk");
  return { ...defaultBridgeSdk, ...(partial ?? {}) };
}
