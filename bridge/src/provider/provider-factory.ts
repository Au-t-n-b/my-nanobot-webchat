import { BridgeProvider, createBridgeProviderFromConfigJson } from "./bridge-provider.js";
import type { BridgeProviderOptions } from "./bridge-provider.js";
import { loadBridgeRootConfig } from "../config/loader.js";

export function createBridgeProvider(configPath?: string, overrides?: Partial<BridgeProviderOptions>): BridgeProvider {
  const raw = loadBridgeRootConfig(configPath);
  return createBridgeProviderFromConfigJson(raw, overrides);
}

export { BridgeProvider, createBridgeProviderFromConfigJson } from "./bridge-provider.js";
