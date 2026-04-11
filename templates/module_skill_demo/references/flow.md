# demo_compliance 流程（参考）

1. 助手调用 `module_skill_runtime`：`module_id=module_skill_demo`，`action=guide`。
2. 用户在引导卡上点击「启动」或助手调用 `action=start`。
3. `choose_standard` → 用户选择标准 → 前端发送 `module_action`，`action=upload_material`，`state.standard` 为选项 id。
4. 用户上传文件 → 前端发送 `after_upload`，携带 `state.upload` 与 `cardId`。
5. 助手调用 `action=finish`（可带 `state.passed` / `state.failed`）生成报告与产物行。

Fast-path 用户消息为 JSON：`{"type":"chat_card_intent",...}`，由 `/api/chat` 在进模型前拦截处理。
