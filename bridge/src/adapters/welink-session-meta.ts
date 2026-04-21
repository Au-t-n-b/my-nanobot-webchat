import { ProviderCommandError } from "../spi/errors.js";

export interface WelinkCreateSessionMeta {
  sendUserAccount: string;
  topicId: string | number;
}

/**
 * BFF convention: `createSession.title` is JSON:
 * `{"welink":{"sendUserAccount":"...","topicId":...}}`
 */
export function parseWelinkCreateSessionTitle(title: string | undefined): WelinkCreateSessionMeta {
  if (!title || !title.trim()) {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "createSession.title is required for WeLink binding (JSON with welink.sendUserAccount and welink.topicId)",
      details: { reason: "missing_title" },
    });
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(title) as unknown;
  } catch {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "createSession.title must be valid JSON for WeLink binding",
      details: { reason: "title_not_json" },
    });
  }
  if (!parsed || typeof parsed !== "object") {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "createSession.title JSON must be an object",
      details: { reason: "title_not_object" },
    });
  }
  const w = (parsed as { welink?: unknown }).welink;
  if (!w || typeof w !== "object") {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "createSession.title must include .welink object",
      details: { reason: "missing_welink" },
    });
  }
  const sendUserAccount = String((w as { sendUserAccount?: unknown }).sendUserAccount ?? "").trim();
  const topicIdRaw = (w as { topicId?: unknown }).topicId;
  if (!sendUserAccount) {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "welink.sendUserAccount is required",
      details: { reason: "missing_send_user" },
    });
  }
  if (
    topicIdRaw === undefined ||
    topicIdRaw === null ||
    topicIdRaw === "" ||
    (typeof topicIdRaw !== "string" && typeof topicIdRaw !== "number")
  ) {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "welink.topicId is required (string or number)",
      details: { reason: "missing_topic_id" },
    });
  }
  const topicId = topicIdRaw as string | number;
  return { sendUserAccount, topicId };
}

export function welinkThreadId(meta: WelinkCreateSessionMeta): string {
  return `welink:${meta.sendUserAccount}:${String(meta.topicId)}`;
}
