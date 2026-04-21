export type InternalThreadId = string;

export interface InternalChatCredentials {
  assistantId: string;
  assistantSecret: string;
}

export type InternalStreamChunk =
  | { kind: "text"; text: string }
  | { kind: "done"; usage?: unknown }
  | { kind: "aborted" }
  | { kind: "error"; message: string; retryable?: boolean; details?: Record<string, unknown> };
