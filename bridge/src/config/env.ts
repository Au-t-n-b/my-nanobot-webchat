import type { InternalChatConfigShape } from "./bridge-config.js";
import type { InternalChatCredentials } from "../adapters/internal-chat-types.js";
import { ProviderCommandError } from "../spi/errors.js";

export function resolveInternalChatCredentials(cfg: InternalChatConfigShape): InternalChatCredentials {
  const idName = cfg.assistant_id_env || "INTERNAL_CHAT_ASSISTANT_ID";
  const secName = cfg.assistant_secret_env || "INTERNAL_CHAT_ASSISTANT_SECRET";
  const assistantId = (
    process.env[idName]?.trim() ||
    process.env.INTERNAL_CHAT_ASSISTANT_ID?.trim() ||
    ""
  ).trim();
  const assistantSecret = (
    process.env[secName]?.trim() ||
    process.env.INTERNAL_CHAT_ASSISTANT_SECRET?.trim() ||
    ""
  ).trim();
  return { assistantId, assistantSecret };
}

export function requireInternalChatCredentials(cfg: InternalChatConfigShape): InternalChatCredentials {
  const c = resolveInternalChatCredentials(cfg);
  if (!c.assistantId) {
    throw new ProviderCommandError({
      code: "invalid_input",
      message: "Assistant id missing: set env per internal_chat.assistant_id_env or INTERNAL_CHAT_ASSISTANT_ID",
      details: { env: cfg.assistant_id_env },
    });
  }
  if (!c.assistantSecret) {
    throw new ProviderCommandError({
      code: "invalid_input",
      message:
        "Assistant secret missing: set env per internal_chat.assistant_secret_env or INTERNAL_CHAT_ASSISTANT_SECRET",
      details: { env: cfg.assistant_secret_env },
    });
  }
  return c;
}
