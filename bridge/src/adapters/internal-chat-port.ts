import type { InternalChatCredentials, InternalStreamChunk, InternalThreadId } from "./internal-chat-types.js";
import type { WelinkCreateSessionMeta } from "./welink-session-meta.js";

export interface CreateThreadInput {
  traceId: string;
  title?: string;
  credentials: InternalChatCredentials;
  welink: WelinkCreateSessionMeta;
}

export interface InternalChatPort {
  ping(traceId: string, credentials: InternalChatCredentials): Promise<void>;

  createThread(input: CreateThreadInput): Promise<{ threadId: InternalThreadId }>;

  closeThread(input: {
    traceId: string;
    threadId: InternalThreadId;
    credentials: InternalChatCredentials;
  }): Promise<void>;

  abortThread(input: {
    traceId: string;
    threadId: InternalThreadId;
    runId?: string;
    credentials: InternalChatCredentials;
  }): Promise<void>;

  streamAssistantReply(input: {
    traceId: string;
    runId: string;
    threadId: InternalThreadId;
    userText: string;
    credentials: InternalChatCredentials;
    welink: WelinkCreateSessionMeta;
    messageId: string;
    signal?: AbortSignal;
  }): AsyncIterable<InternalStreamChunk>;

  replyQuestion(input: {
    traceId: string;
    threadId: InternalThreadId;
    toolCallId: string;
    answer: string;
    credentials: InternalChatCredentials;
  }): Promise<void>;

  replyPermission(input: {
    traceId: string;
    threadId: InternalThreadId;
    permissionId: string;
    response: "once" | "always" | "reject";
    credentials: InternalChatCredentials;
  }): Promise<void>;
}
