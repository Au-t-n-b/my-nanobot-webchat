# Docs Index（Skill-First / SDUI）

本目录面向两类读者提供两条“最短阅读路径”：

- **业务 Skill 开发者（写阶段 Skill / 大盘 / 工作台）**：从“Skill 开发者路径”开始
- **平台开发/维护者（前后端/协议/运行时）**：从“平台维护者路径”开始

---

## Skill 开发者路径（同事写阶段 Skill）

按顺序阅读：

1. **阶段 Skill Starter（直接复制改名可跑）**  
   - [`docs/skill/stage-starters.md`](./skill/stage-starters.md)  
   - 代码模板目录：仓库根的 `skill-starters/`

2. **Skill-First 接入规范（事件、HITL、EmbeddedWeb、边界铁律）**  
   - [`docs/skill/guide.md`](./skill/guide.md)

3. **SDUI 协议（节点白名单、Action、Patch 约束）**  
   - [`docs/sdui/protocol.md`](./sdui/protocol.md)

4. **实时 Patch 手册（syntheticPath/docId/revision 与推送姿势）**  
   - [`docs/skill/dev-manual.md`](./skill/dev-manual.md)

5. **Cursor SOP（用 AI 从零构建阶段 Skill）**  
   - [`docs/skill/cursor-sop.md`](./skill/cursor-sop.md)

你需要对照的“真实参考实现”（本机用户目录）：  
`~/.nanobot/workspace/skills/{job_management,smart_survey,jmfz}`

---

## 平台维护者路径（协议/运行时/架构）

1. **Skill Runtime / async-resume 核心语义**  
   - Skill 事件白名单与边界：[`docs/skill/guide.md`](./skill/guide.md)  
   - 运行时与补丁：[`docs/skill/dev-manual.md`](./skill/dev-manual.md)

2. **混合模式（受控子任务）**  
   - 协议：[`docs/runtime/hybrid-mode-protocol.md`](./runtime/hybrid-mode-protocol.md)  
   - 治理：[`docs/runtime/hybrid-mode-governance.md`](./runtime/hybrid-mode-governance.md)

3. **SDUI 协议与 Schema**  
   - 协议：[`docs/sdui/protocol.md`](./sdui/protocol.md)  
   - Schema：[`docs/sdui/schema-v2.json`](./sdui/schema-v2.json)、[`docs/sdui/schema-v3.json`](./sdui/schema-v3.json)  
   - 示例：[`docs/sdui/examples/`](./sdui/examples/)

4. **渠道插件（如需）**  
   - [`docs/channels/plugin-guide.md`](./channels/plugin-guide.md)

---

## 设计与计划（Design / Plans）

如果你在做架构演进、协议变更、前端大改版等，去这里找历史设计/计划/交接材料：

- 设计稿：`docs/design/specs/`
- 实施计划：`docs/design/plans/`
- 交接：`docs/design/handoffs/`
- 视觉规范：`docs/design/visual-spec-v1.md`

