export type ProviderModelSuggestion = {
  /** Suggested default model when the provider is selected */
  defaultModel: string;
  /** Suggested quick-switch models (each line in Config Center) */
  models: string[];
};

/**
 * Provider → recommended models.
 *
 * Source-of-truth: public provider docs / release notes (last ~6 months),
 * supplemented with widely-used stable IDs when providers expose aliases.
 *
 * Notes:
 * - Gateways (openrouter/aihubmix/siliconflow/volcengine/byteplus) can route
 *   many upstream models; we only provide common starter IDs.
 * - Local providers (ollama/vllm/ovms) are environment-specific; keep minimal.
 */
export const PROVIDER_MODEL_SUGGESTIONS: Record<string, ProviderModelSuggestion> = {
  // Zhipu / Z.ai (GLM)
  // https://docs.z.ai/release-notes/new-released
  zhipu: {
    defaultModel: "glm-5",
    models: [
      "glm-5",
      "glm-5-turbo",
      "glm-4.7",
      "glm-4.7-flash",
      "glm-4.6",
      "glm-4.6v",
    ],
  },

  // DashScope (Qwen)
  // Qwen lineup changes frequently; these are common stable IDs / families.
  // See: https://docs.litellm.ai/docs/providers/dashscope and vendor catalogs.
  dashscope: {
    defaultModel: "qwen-max",
    models: [
      "qwen-max",
      "qwen-plus",
      "qwen-turbo",
      "qwen-vl-max",
      "qwen-vl-plus",
      "qwen2.5-72b-instruct",
      "qwen3-32b",
      "qwen3-235b-a22b",
    ],
  },

  // Moonshot (Kimi)
  // https://platform.moonshot.ai/docs/
  moonshot: {
    defaultModel: "kimi-k2.5",
    models: [
      "kimi-k2.5",
      "kimi-k2-turbo-preview",
      "kimi-k2-thinking",
    ],
  },

  // MiniMax
  // https://platform.minimax.io/docs/release-notes/models
  minimax: {
    defaultModel: "MiniMax-M2.7",
    models: [
      "MiniMax-M2.7",
      "MiniMax-M2.7-highspeed",
      "MiniMax-M2.5",
      "MiniMax-M2.5-highspeed",
      "MiniMax-M2.1",
      "MiniMax-M2",
      "MiniMax-Text-01",
    ],
  },

  // DeepSeek
  // https://api-docs.deepseek.com/updates/
  deepseek: {
    defaultModel: "deepseek-chat",
    models: [
      "deepseek-chat",
      "deepseek-reasoner",
      "DeepSeek-V3.2",
      "DeepSeek-R1",
    ],
  },

  // Gemini
  // https://ai.google.dev/gemini-api/docs/models
  gemini: {
    defaultModel: "gemini-2.5-pro",
    models: [
      "gemini-3.1-pro-preview",
      "gemini-3-flash-preview",
      "gemini-3.1-flash-lite-preview",
      "gemini-2.5-pro",
      "gemini-2.5-flash",
      "gemini-2.5-flash-lite",
    ],
  },

  // Anthropic
  // https://docs.anthropic.com/en/docs/about-claude/models/all-models
  anthropic: {
    defaultModel: "claude-sonnet-4-6",
    models: [
      "claude-opus-4-6",
      "claude-sonnet-4-6",
      "claude-haiku-4-5",
      "claude-sonnet-4-5",
      "claude-opus-4-5",
    ],
  },

  // OpenAI
  // https://platform.openai.com/api/docs/models
  openai: {
    defaultModel: "gpt-5.4",
    models: [
      "gpt-5.4",
      "gpt-5.4-mini",
      "gpt-5.4-nano",
      "gpt-realtime-1.5",
      "gpt-image-1.5",
    ],
  },

  // Groq (hosted OSS)
  // https://console.groq.com/docs/models
  groq: {
    defaultModel: "llama-3.3-70b-versatile",
    models: [
      "llama-3.1-8b-instant",
      "llama-3.3-70b-versatile",
      "openai/gpt-oss-120b",
      "openai/gpt-oss-20b",
      "groq/compound",
      "groq/compound-mini",
    ],
  },

  // Mistral
  // https://docs.mistral.ai/models
  mistral: {
    defaultModel: "mistral-large-3-25-12",
    models: [
      "mistral-large-3-25-12",
      "mistral-small-4.0-26-03",
      "mistral-medium-3.1-25-08",
      "codestral-25-08",
      "devstral-2-25-12",
    ],
  },

  // Gateways: keep minimal starters (actual catalog depends on provider)
  openrouter: {
    defaultModel: "anthropic/claude-sonnet-4-6",
    models: [
      "anthropic/claude-sonnet-4-6",
      "anthropic/claude-opus-4-6",
      "openai/gpt-5.4",
      "zhipu/glm-5",
      "google/gemini-2.5-pro",
    ],
  },
  aihubmix: {
    defaultModel: "gpt-5.4",
    models: ["gpt-5.4", "gpt-5.4-mini", "claude-sonnet-4-6", "glm-5", "gemini-2.5-pro"],
  },
  siliconflow: {
    defaultModel: "gpt-5.4",
    models: ["gpt-5.4", "gpt-5.4-mini", "claude-sonnet-4-6", "glm-5", "gemini-2.5-pro"],
  },
  volcengine: {
    defaultModel: "doubao-seed-1.6",
    models: ["doubao-seed-1.6", "doubao-pro", "doubao-lite"],
  },
  volcengine_coding_plan: {
    defaultModel: "doubao-seed-1.6",
    models: ["doubao-seed-1.6", "doubao-pro", "doubao-lite"],
  },
  byteplus: {
    defaultModel: "doubao-seed-1.6",
    models: ["doubao-seed-1.6", "doubao-pro", "doubao-lite"],
  },
  byteplus_coding_plan: {
    defaultModel: "doubao-seed-1.6",
    models: ["doubao-seed-1.6", "doubao-pro", "doubao-lite"],
  },

  // Local / custom: keep placeholders
  ollama: { defaultModel: "llama3.2", models: ["llama3.2", "qwen2.5", "deepseek-r1"] },
  vllm: { defaultModel: "local-model", models: ["local-model"] },
  ovms: { defaultModel: "local-model", models: ["local-model"] },
  custom: { defaultModel: "default", models: ["default"] },
  azure_openai: { defaultModel: "your-deployment-name", models: ["your-deployment-name"] },
};

