/** Local mirror of agent-bridge-sdk v2 public SPI (see repo docs / platform contract). */

export interface ProviderRuntimeContext {
  outbound: RuntimeOutboundEmitter;
}

export interface RuntimeOutboundEmitter {
  emitOutboundMessage(input: EmitOutboundMessageInput): Promise<{ applied: true }>;
}

export interface ThirdPartyAgentProvider {
  initialize?(context: ProviderRuntimeContext): Promise<void>;

  health(input: ProviderHealthInput): Promise<ProviderHealthResult>;

  createSession(input: ProviderCreateSessionInput): Promise<ProviderCreateSessionResult>;

  runMessage(input: ProviderRunMessageInput): Promise<ProviderRun>;

  replyQuestion(input: ProviderQuestionReplyInput): Promise<{ applied: true }>;

  replyPermission(input: ProviderPermissionReplyInput): Promise<{ applied: true }>;

  closeSession(input: ProviderCloseSessionInput): Promise<{ applied: true }>;

  abortSession(input: ProviderAbortSessionInput): Promise<{ applied: true }>;

  dispose?(): Promise<void>;
}

export interface ProviderHealthInput {
  traceId: string;
}

export interface ProviderHealthResult {
  online: boolean;
}

export interface ProviderCreateSessionInput {
  traceId: string;
  title?: string;
  assistantId?: string;
}

export interface ProviderCreateSessionResult {
  toolSessionId: string;
  title?: string;
}

export interface ProviderRunMessageInput {
  traceId: string;
  runId: string;
  toolSessionId: string;
  text: string;
  assistantId?: string;
}

export interface ProviderQuestionReplyInput {
  traceId: string;
  toolSessionId: string;
  toolCallId: string;
  answer: string;
}

export interface ProviderPermissionReplyInput {
  traceId: string;
  toolSessionId: string;
  permissionId: string;
  response: "once" | "always" | "reject";
}

export interface ProviderCloseSessionInput {
  traceId: string;
  toolSessionId: string;
}

export interface ProviderAbortSessionInput {
  traceId: string;
  toolSessionId: string;
  runId?: string;
}

export interface EmitOutboundMessageInput {
  toolSessionId: string;
  messageId: string;
  trigger: "scheduled" | "webhook" | "system" | (string & {});
  facts: AsyncIterable<OutboundFact>;
  assistantId?: string;
}

export interface ProviderRun {
  runId: string;
  facts: AsyncIterable<ProviderFact>;
  result(): Promise<ProviderTerminalResult>;
}

export interface ProviderTerminalResult {
  outcome: "completed" | "failed" | "aborted";
  usage?: unknown;
  error?: ProviderError;
}

export interface ProviderError {
  code:
    | "not_found"
    | "invalid_input"
    | "not_supported"
    | "timeout"
    | "rate_limited"
    | "provider_unavailable"
    | "internal_error";
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export type ProviderFact =
  | MessageStartFact
  | TextDeltaFact
  | TextDoneFact
  | ThinkingDeltaFact
  | ThinkingDoneFact
  | ToolUpdateFact
  | QuestionAskFact
  | PermissionAskFact
  | MessageDoneFact
  | SessionErrorFact;

export type OutboundFact = ProviderFact;

export interface MessageStartFact {
  type: "message.start";
  toolSessionId: string;
  messageId: string;
  raw?: unknown;
}

export interface TextDeltaFact {
  type: "text.delta";
  toolSessionId: string;
  messageId: string;
  partId: string;
  content: string;
  raw?: unknown;
}

export interface TextDoneFact {
  type: "text.done";
  toolSessionId: string;
  messageId: string;
  partId: string;
  content: string;
  raw?: unknown;
}

export interface ThinkingDeltaFact {
  type: "thinking.delta";
  toolSessionId: string;
  messageId: string;
  partId: string;
  content: string;
  raw?: unknown;
}

export interface ThinkingDoneFact {
  type: "thinking.done";
  toolSessionId: string;
  messageId: string;
  partId: string;
  content: string;
  raw?: unknown;
}

export interface ToolUpdateFact {
  type: "tool.update";
  toolSessionId: string;
  messageId: string;
  partId: string;
  toolCallId: string;
  toolName: string;
  status: "pending" | "running" | "completed" | "error";
  title?: string;
  input?: unknown;
  output?: unknown;
  error?: string;
  raw?: unknown;
}

export interface QuestionAskFact {
  type: "question.ask";
  toolSessionId: string;
  messageId: string;
  toolCallId: string;
  header?: string;
  question: string;
  options?: string[];
  context?: Record<string, unknown>;
  raw?: unknown;
}

export interface PermissionAskFact {
  type: "permission.ask";
  toolSessionId: string;
  messageId: string;
  permissionId: string;
  toolCallId?: string;
  permissionType?: string;
  metadata?: Record<string, unknown>;
  raw?: unknown;
}

export interface MessageDoneFact {
  type: "message.done";
  toolSessionId: string;
  messageId: string;
  reason?: string;
  tokens?: unknown;
  cost?: number;
  raw?: unknown;
}

/** Session-level fact per v2 draft (no messageId on type). */
export interface SessionErrorFact {
  type: "session.error";
  toolSessionId: string;
  error: ProviderError;
  raw?: unknown;
}
