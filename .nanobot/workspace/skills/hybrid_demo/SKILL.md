# Hybrid Demo Skill

---
name: hybrid_demo
description: 用于验证 Skill-First 混合子任务（skill.agent_task_execute）的最小样例。
version: 0.1.0
tags: [hybrid, demo]
---

这是一个用于测试混合模式的最小 Skill：

- driver 负责主流程与 SDUI patch
- bridge 负责执行受控 Agent 子任务（白名单工具 + 沙箱）

