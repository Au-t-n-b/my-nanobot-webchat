# @nanobot/agent-bridge-provider

TypeScript implementation of **ThirdPartyAgentProvider** (agent-bridge-sdk **v2** draft), loaded by the **company platform Runtime**. This package is **not** wired to nanobot `AgentLoop` or chat `channel`s.

## WeLink session (MVP)

v2 `runMessage` does not carry `sendUserAccount` / `topicId`. The **BFF / gateway** must pass WeLink identity in `createSession.title` as JSON:

```json
{"welink":{"sendUserAccount":"user@example.com","topicId":"topic-123"}}
```

The provider generates a cryptographically random **`toolSessionId`** (`sess_` + UUID) and maps it internally to the same thread key nanobot AGUI uses: `welink:{sendUserAccount}:{topicId}`.

## Optional backend: nanobot `/welink/chat/stream`

`WelinkNanobotProxyAdapter` POSTs to `{ internal_chat.api_base_url }{ internal_chat.stream_path }` (default path `/welink/chat/stream`) with the same JSON body as [nanobot web routes](../nanobot/web/routes.py). If `WELINK_AUTH_TOKEN` is set on the AGUI server, set the same token in the environment name from `internal_chat.welink_auth_token_env` (default `WELINK_AUTH_TOKEN`) so the adapter can send `Authorization`.

## Configuration (`~/.nanobot/config.json`)

Mirror fields (camelCase or snake_case) are accepted by Python; this package reads the same file when using `createBridgeProvider()`:

- `bridge_sdk`: `enabled`, `provider_id`, concurrency limits (reserved).
- `internal_chat`: `api_base_url`, `stream_path`, `timeout_ms`, env var names for assistant id/secret and WeLink token.

**Secrets**: only `process.env` — use `INTERNAL_CHAT_ASSISTANT_ID`, `INTERNAL_CHAT_ASSISTANT_SECRET`, and optionally `WELINK_AUTH_TOKEN`.

## Operations

- **In-memory session registry**: scale-out requires sticky routing or a future persistent registry.
- **replyQuestion / replyPermission**: `WelinkNanobotProxyAdapter` throws `ProviderCommandError` `not_supported` until the host exposes APIs.
- **Logs**: do not print raw secrets; use redacted headers where applicable.

## Scripts

```bash
npm install
npm run typecheck
npm test
```

### Path B：本机冒烟（Provider → AGUI `/welink/chat/stream`）

与早期「WeLink 助手广场」直连式尝试不同，这里验证的是 **v2 `BridgeProvider` + `WelinkNanobotProxyAdapter`**（供平台 Runtime 加载的同一条能力链）。

1. 启动本机 **AGUI**（`npm run dev` 或 `python -m nanobot agui`，端口以实际为准）。  
2. 在 **`~/.nanobot/config.json`** 配置 `internalChat.apiBaseUrl`（或 `internal_chat.api_base_url`）指向该 AGUI 根地址。  
3. 导出 **`INTERNAL_CHAT_ASSISTANT_ID`**、**`INTERNAL_CHAT_ASSISTANT_SECRET`**（本地测试可为任意非空字符串）；若 AGUI 为 `/welink/chat/stream` 启用了鉴权，再设置 **`WELINK_AUTH_TOKEN`**。  
4. 在 **`bridge/`** 目录执行：

```bash
npm run smoke:local
```

可选环境变量：`SMOKE_SEND_USER`、`SMOKE_TOPIC_ID`、`SMOKE_TEXT`。成功时终端会打印流式 `text.delta` 与 `result()` 为 `completed`。

## Legacy WhatsApp bridge

The old Baileys package lives at **`bridge-legacy-whatsapp/`** at the repository root (wheel path `nanobot/whatsapp_bridge_legacy`). It is unrelated to this provider.
