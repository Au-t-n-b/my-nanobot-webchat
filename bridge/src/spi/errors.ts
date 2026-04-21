import type { ProviderError } from "./types.js";

export type ProviderCommandErrorCode =
  | "invalid_input"
  | "not_found"
  | "not_supported"
  | "provider_unavailable"
  | "internal_error";

export interface ProviderCommandErrorInit {
  code: ProviderCommandErrorCode;
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

/** Command application phase — reject/throw this, never use as ProviderTerminalResult.error. */
export class ProviderCommandError extends Error {
  readonly code: ProviderCommandErrorCode;
  readonly retryable?: boolean;
  readonly details?: Record<string, unknown>;

  constructor(init: ProviderCommandErrorInit) {
    super(init.message);
    this.name = "ProviderCommandError";
    this.code = init.code;
    this.retryable = init.retryable;
    this.details = init.details;
  }
}

export function providerError(init: {
  code: ProviderError["code"];
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}): ProviderError {
  return { ...init };
}
