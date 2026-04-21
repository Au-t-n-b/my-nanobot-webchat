import type { ProviderCommandError } from "./errors.js";

export function isProviderCommandError(e: unknown): e is ProviderCommandError {
  return e instanceof Error && e.name === "ProviderCommandError" && "code" in e;
}
