export type ToolSessionIdSource = "provider" | "platform";

export interface SessionRecord {
  toolSessionId: string;
  threadId: string;
  toolSessionIdSource: ToolSessionIdSource;
  createdAtMs: number;
  title?: string;
  assistantId?: string;
  /** WeLink / BFF context (never exposed as external session key). */
  welink?: {
    sendUserAccount: string;
    topicId: string | number;
  };
}
