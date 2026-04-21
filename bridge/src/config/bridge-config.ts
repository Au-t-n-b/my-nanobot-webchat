export interface BridgeSdkConfigShape {
  enabled: boolean;
  provider_id: string;
  max_concurrent_runs_per_session: number;
  max_concurrent_outbound_per_session: number;
}

export interface InternalChatConfigShape {
  api_base_url: string;
  assistant_id_env: string;
  assistant_secret_env: string;
  welink_auth_token_env: string;
  timeout_ms: number;
  stream_path: string;
}

export interface BridgeRootConfigShape {
  bridge_sdk?: Partial<BridgeSdkConfigShape>;
  internal_chat?: Partial<InternalChatConfigShape>;
}

export const defaultBridgeSdk: BridgeSdkConfigShape = {
  enabled: true,
  provider_id: "nanobot-internal-chat",
  max_concurrent_runs_per_session: 1,
  max_concurrent_outbound_per_session: 1,
};

export const defaultInternalChat: InternalChatConfigShape = {
  api_base_url: "",
  assistant_id_env: "INTERNAL_CHAT_ASSISTANT_ID",
  assistant_secret_env: "INTERNAL_CHAT_ASSISTANT_SECRET",
  welink_auth_token_env: "WELINK_AUTH_TOKEN",
  timeout_ms: 60_000,
  stream_path: "/welink/chat/stream",
};
