# Skill 开发者接入协议与交互规范

> 平台只提供通用运行时与盲转发。业务主权、状态编排、数据解释、步骤推进、异常降级，完全归属 Skill 开发者。
>
> 平台不是业务编排器。平台不是业务状态机。平台不是业务摘要生成器。平台不是业务大盘拼装器。
>
> Skill 是唯一业务真源。任何试图将 `next step`、缺件判断、业务指标计算、业务摘要生成回退到平台侧的实现，均视为协议违规。

---

## 1. 文档目的

本文档定义 Nanobot/Claw `Skill-First` 架构下，业务 Skill 接入平台时必须遵守的接口契约、交互规范与边界规则。

适用对象：

- 业务 Skill 开发者
- Dashboard 业务开发者
- Embedded Web 业务开发者
- 平台运行时维护者

本文档是规范，不是建议。

---

## 2. 架构铁律

### 2.1 单一业务真源

业务流程、业务状态、业务判断、业务摘要、业务指标、业务产物，必须由 Skill 自身定义并输出。

平台不得：

- 判断缺少哪些业务文件
- 推断下一步是什么
- 生成业务摘要
- 计算业务指标
- 决定按钮点下去后该走哪条业务分支

### 2.2 平台职责上限

平台只负责四件事：

- 运行与唤醒 Skill 进程
- 持久化挂起中的 HITL 请求
- 渲染通用 UI 容器
- 将前端结果原样回传给 Skill

平台不解释业务。平台只转发。

### 2.3 Skill 职责下限

Skill 必须自行负责：

- 定义状态机
- 定义动作标识
- 定义降级路由
- 定义 dashboard 数据
- 定义产物内容
- 定义人类介入点与恢复逻辑

如果 Skill 不能在没有平台业务 if/else 的前提下独立恢复运行，则该 Skill 设计不合格。

---

## 3. 架构原语：UI 空间划分（三分天下）

### 3.1 左侧：Input & Action

左侧是聊天流，是 Skill 与用户的专属控制台。

左侧负责：

- 普通文本消息
- 引导消息
- 所有 HITL 卡片
- 表单
- 文件上传
- 选项选择
- 二次确认

左侧不负责：

- 展示业务大盘主视图
- 承担业务最终产物预览

硬规则：

- 所有用户交互入口必须能收敛为一次意图回传
- 所有 HITL 卡片必须在左侧渲染
- 左侧触发的所有动作，最终必须统一回流到 `/api/chat`

### 3.2 中栏：State & Workspace

中栏是主工作台，即 `DashboardNavigator`。

中栏负责：

- 展示业务 Dashboard
- 展示步骤进展
- 展示指标卡
- 展示上传文件列表
- 展示业务产物索引
- 展示业务自定义卡片

中栏不负责：

- 解释业务语义
- 猜测缺件
- 替 Skill 推进流程

硬规则：

- 中栏只能由 `dashboard.*` 数据驱动
- 平台不得在中栏写入模块专属业务逻辑
- 中栏任何节点的内容，都必须能追溯到 Skill 输出

### 3.3 右侧：Output & Reference

右侧是 `PreviewPanel`，只负责产物与参考资料渲染。

右侧负责：

- 文件预览
- 图片预览
- Excel 预览
- 网页预览
- 参考资料预览

右侧不负责：

- 承担业务状态机
- 决定展示什么业务步骤
- 生成业务摘要

硬规则：

- 右侧仅渲染 `artifact.publish` 已发布对象
- 右侧不接受业务私有状态直接写入
- 右侧只认逻辑 URI / artifact 引用，不认业务物理路径

---

## 4. 通信协议：单向数据流

## 4.1 下行：Skill -> 平台呈现

Skill 进程通过标准输出打印 runtime event，平台读取后执行盲转发。

当前标准事件包括：

- `chat.guidance`
- `dashboard.bootstrap`
- `dashboard.patch`
- `hitl.file_request`
- `hitl.choice_request`
- `hitl.confirm_request`
- `artifact.publish`
- `task_progress.sync`

规范要求：

- Skill 只输出数据与动作意图
- 平台只消费 event envelope
- 平台不得改写 Skill 的业务含义

### 4.2 上行：Skill UI -> 平台

所有前端操作，最终统一通过 `/api/chat` 回传 intent。

标准意图：

- `skill_runtime_result`
- `skill_runtime_start`
- `skill_runtime_resume`

其中，HITL 完成后的主通道是：

- `intent.verb = "skill_runtime_result"`

硬规则：

- 平台只校验 envelope 完整性、线程一致性、幂等合法性
- 平台不得将前端结果二次翻译成业务逻辑
- 平台不得替 Skill 决定恢复动作

---

## 5. 交互双轨制：SDUI 与 EmbeddedWeb

## 5.1 轻交互：原生 SDUI

适用场景：

- 普通步进
- 指标展示
- 状态摘要
- 文件列表
- 产物索引
- 轻表单
- 按钮点击
- 选择卡片

开发方式：

- 在 `dashboard.json` 中声明节点
- 节点事件通过平台统一触发 `post_user_message`
- 最终收敛为 `/api/chat` 的 runtime intent

硬规则：

- SDUI 只负责通用渲染
- SDUI 节点不能承载业务状态真源
- 业务判断必须回到 Skill 进程执行

## 5.2 重交互：EmbeddedWeb

适用场景：

- 甘特图
- 复杂拓扑图
- 大型关系图
- 高交互编辑器
- 原生 SDUI 无法表达的业务视图

开发方式：

- 开发者提供静态 HTML，例如 `job_workbench.html`
- 平台以 `iframe` 方式嵌入

`iframe` 内部必须通过 `window.parent.postMessage` 向平台发送事件。

规范消息类型：

```json
{
  "type": "skill_web_intent",
  "payload": {
    "skillName": "job_management",
    "action": "confirm_schedule",
    "data": {
      "taskId": "task-001"
    }
  }
}
```

平台职责：

- 校验消息来源
- 提取 `skill_web_intent`
- 原样盲透传 payload 至后端

平台禁止：

- 解析 Embedded Web 内部业务结构
- 替开发者缓存页面草稿
- 将网页点击解释成平台私有业务动作

## 5.3 状态隔离

Embedded Web 的中间态、草稿态、编辑器态，必须由 Skill 自行维护。

推荐落盘文件：

- `runtime/ui_state.json`
- `runtime/draft.json`
- `runtime/session_state.json`

硬规则：

- 平台不替业务记草稿
- 平台不替业务恢复网页编辑状态
- 平台只保证消息通道与唤醒能力

---

## 6. HITL 异步交互协议

这是核心章节。

## 6.1 Yield & Resume 理念

Skill 进程必须被视为无状态且短命。

当业务需要人类介入时，Skill 必须：

1. 输出一个 `hitl.*` 请求事件
2. 立即退出本次运行
3. 将后续恢复入口显式交给 `resumeAction` 或 `onCancelAction`

这叫 `Yield`。

平台随后负责：

1. 持久化挂起请求
2. 渲染左侧 HITL 卡片
3. 等待用户操作
4. 通过 `/api/chat` 回传 `skill_runtime_result`
5. 重新唤醒 Skill 进程

这叫 `Resume`。

硬规则：

- Skill 不得阻塞等待用户输入
- Skill 不得假定进程内内存会跨次存在
- Skill 不得依赖平台替它保存业务状态

## 6.2 通用 Envelope

所有 `hitl.*` 请求都必须包含以下顶层元数据：

```json
{
  "threadId": "thread-001",
  "skillName": "smart_survey_workbench",
  "skillRunId": "run-step1-001",
  "event": "hitl.file_request",
  "payload": {
    "requestId": "req-step1-upload-001"
  }
}
```

关键字段：

- `threadId`
- `skillName`
- `requestId`
- `event`
- `payload`

## 6.3 三大强契约护法字段

以下字段为必填字段，且都位于 `payload` 内部。

### `requestId`

用途：

- 标识一次挂起请求
- 保证幂等消费
- 保证重复点击不会造成重复恢复

硬规则：

- 同一请求必须复用同一个 `requestId`
- Skill 不得为同一挂起点生成多个语义不同的 `requestId`

### `resumeAction`

用途：

- 用户成功完成交互后，平台恢复 Skill 时切入的状态机动作标识

硬规则：

- `resumeAction` 必须是 Skill 自己认识的动作
- 平台不得推断、改写或代填 `resumeAction`

### `onCancelAction`

用途：

- 用户取消
- 平台超时
- 平台返回错误
- Skill 需要降级

时的统一回退动作标识。

硬规则：

- 每个 `hitl.*` 请求都必须定义 `onCancelAction`
- 平台只回传状态，不决定降级策略
- Skill 必须显式处理 `fallback_cancel`

---

## 7. 三类核心 HITL 请求规范

## 7.1 `hitl.file_request`

用途：

- 请求用户上传一个或多个文件

示例：

```json
{
  "threadId": "thread-001",
  "skillName": "smart_survey_workbench",
  "skillRunId": "run-step1-001",
  "event": "hitl.file_request",
  "payload": {
    "requestId": "req-upload-step1-001",
    "title": "请上传 Step1 输入底表",
    "accept": ".xlsx,.docx",
    "mount": "workspace://smart-survey/input/step1",
    "multiple": true,
    "resumeAction": "resume_after_upload",
    "onCancelAction": "fallback_cancel"
  }
}
```

字段说明：

- `accept`：允许的文件类型
- `mount`：逻辑挂载点
- `multiple`：是否允许多个文件
- `resumeAction`：成功恢复动作
- `onCancelAction`：失败或取消恢复动作

硬规则：

- 平台唤醒时只允许返回逻辑 URI
- 绝对禁止返回物理路径
- Skill 必须自行检查文件是否满足业务要求

合法返回：

```json
{
  "type": "skill_runtime_result",
  "threadId": "thread-001",
  "skillName": "smart_survey_workbench",
  "requestId": "req-upload-step1-001",
  "status": "ok",
  "result": {
    "files": [
      {
        "name": "sample_BOQ.xlsx",
        "uri": "workspace://smart-survey/input/step1/sample_BOQ.xlsx"
      }
    ]
  }
}
```

非法返回：

```json
{
  "result": {
    "files": [
      {
        "path": "C:\\Users\\xxx\\Desktop\\sample_BOQ.xlsx"
      }
    ]
  }
}
```

上例违反协议，必须拒绝。

## 7.2 `hitl.choice_request`

用途：

- 请求用户单选或多选

示例：

```json
{
  "threadId": "thread-001",
  "skillName": "job_management",
  "skillRunId": "run-choice-001",
  "event": "hitl.choice_request",
  "payload": {
    "requestId": "req-choice-strategy-001",
    "title": "请选择输出格式",
    "mode": "single",
    "options": [
      {"id": "html", "label": "生成 HTML"},
      {"id": "md", "label": "生成 Markdown"},
      {"id": "other", "label": "生成其他"}
    ],
    "resumeAction": "resume_after_choice",
    "onCancelAction": "fallback_cancel"
  }
}
```

合法返回：

```json
{
  "type": "skill_runtime_result",
  "threadId": "thread-001",
  "skillName": "job_management",
  "requestId": "req-choice-strategy-001",
  "status": "ok",
  "result": {
    "selectedIds": ["html"]
  }
}
```

硬规则：

- `selectedIds` 必须只包含 Skill 声明过的 option id
- Skill 必须自行决定选中后走哪条业务分支

## 7.3 `hitl.confirm_request`

用途：

- 二次确认
- 危险动作确认
- 流程终止确认

示例：

```json
{
  "threadId": "thread-001",
  "skillName": "job_management",
  "skillRunId": "run-confirm-001",
  "event": "hitl.confirm_request",
  "payload": {
    "requestId": "req-confirm-delete-001",
    "title": "确认结束当前作业流程？",
    "confirmLabel": "确认结束",
    "cancelLabel": "返回",
    "resumeAction": "resume_after_confirm",
    "onCancelAction": "fallback_cancel"
  }
}
```

合法返回：

```json
{
  "type": "skill_runtime_result",
  "threadId": "thread-001",
  "skillName": "job_management",
  "requestId": "req-confirm-delete-001",
  "status": "ok",
  "result": {
    "confirmed": true
  }
}
```

硬规则：

- `confirmed` 只能是布尔值
- 确认后的业务副作用必须由 Skill 自行执行

---

## 8. Dashboard 协议

## 8.1 `dashboard.bootstrap`

用于初始化中栏大盘骨架。

适用场景：

- 进入模块
- 切换业务视图
- 首次启动 dashboard

示例：

```json
{
  "threadId": "thread-001",
  "skillName": "smart_survey_workbench",
  "skillRunId": "run-bootstrap-001",
  "event": "dashboard.bootstrap",
  "payload": {
    "docId": "dashboard:smart-survey-workbench",
    "syntheticPath": "skill-ui://SduiView?dataFile=skills/smart_survey_workbench/data/dashboard.json",
    "document": {
      "type": "SduiDocument",
      "root": {
        "type": "Stack",
        "children": []
      }
    }
  }
}
```

## 8.2 `dashboard.patch`

用于局部更新中栏节点状态。

规范要求：

- 采用 JSON Patch 风格的局部更新语义
- 平台只执行 patch，不解释业务
- patch 必须是幂等或可安全重放的

示例：

```json
{
  "threadId": "thread-001",
  "skillName": "smart_survey_workbench",
  "skillRunId": "run-patch-step1-001",
  "event": "dashboard.patch",
  "payload": {
    "docId": "dashboard:smart-survey-workbench",
    "syntheticPath": "skill-ui://SduiView?dataFile=skills/smart_survey_workbench/data/dashboard.json",
    "ops": [
      {
        "op": "merge",
        "target": {"by": "id", "nodeId": "summary-text"},
        "value": {
          "id": "summary-text",
          "type": "Text",
          "content": "Step1 已完成，已识别液冷/A3/新址新建。"
        }
      }
    ]
  }
}
```

硬规则：

- Skill 输出什么，中栏就显示什么
- 平台不允许在 patch 阶段注入业务默认值
- 平台不允许在 patch 阶段替业务拼摘要

---

## 9. 产物协议

`artifact.publish` 用于向右侧预览区和中栏产物区发布对象。

示例：

```json
{
  "threadId": "thread-001",
  "skillName": "smart_survey_workbench",
  "skillRunId": "run-artifact-001",
  "event": "artifact.publish",
  "payload": {
    "docId": "dashboard:smart-survey-workbench",
    "syntheticPath": "skill-ui://SduiView?dataFile=skills/smart_survey_workbench/data/dashboard.json",
    "items": [
      {
        "artifactId": "artifact-step1-report",
        "label": "定制工勘表.xlsx",
        "uri": "artifact://smart-survey/output/custom-table",
        "kind": "excel",
        "status": "ready"
      }
    ]
  }
}
```

硬规则：

- 只发布逻辑 URI 或 artifactId
- 物理路径属于平台内部实现细节
- 产物预览行为必须与业务编排解耦

---

## 10. 前端回传规范

## 10.1 `/api/chat` 回传 `skill_runtime_result`

HITL 卡片、SDUI 按钮、EmbeddedWeb 触发结果，最终都必须通过 `/api/chat` 进入 runtime fast-path。

标准消息体：

```json
{
  "verb": "skill_runtime_result",
  "payload": {
    "type": "skill_runtime_result",
    "threadId": "thread-001",
    "skillName": "smart_survey_workbench",
    "requestId": "req-upload-step1-001",
    "status": "ok",
    "result": {
      "files": [
        {
          "name": "sample_BOQ.xlsx",
          "uri": "workspace://smart-survey/input/step1/sample_BOQ.xlsx"
        }
      ]
    }
  }
}
```

平台仅做以下校验：

- `type` 合法
- `threadId` 一致
- `skillName` 存在
- `requestId` 存在
- `status` 合法
- 请求幂等

平台不做以下行为：

- 根据业务模块名写 if/else
- 根据文件名猜测业务是否就绪
- 替 Skill 选择恢复分支

## 10.2 EmbeddedWeb 回传 `skill_web_intent`

`iframe` 内消息格式：

```js
window.parent.postMessage(
  {
    type: "skill_web_intent",
    payload: {
      skillName: "job_management",
      requestId: "req-web-001",
      action: "confirm_schedule",
      data: {
        taskId: "task-001",
        range: ["2026-04-16", "2026-04-20"]
      }
    }
  },
  "*"
)
```

平台接收后应执行：

- 来源校验
- 结构校验
- 原样传递至后端 Skill 通道

平台不得执行：

- 业务字段重组
- 草稿状态补写
- 业务语义翻译

---

## 11. 幂等、取消、超时

## 11.1 幂等

同一个 `requestId` 的结果，只能被消费一次。

平台必须：

- 拒绝重复消费
- 允许重复提交但返回幂等成功

Skill 必须：

- 允许相同 `requestId` 安全重放
- 不因重复回调制造重复副作用

## 11.2 取消

当用户取消请求时：

- 平台回传 `status = "cancel"`
- Skill 必须进入 `onCancelAction`

## 11.3 超时

当挂起请求超时时：

- 平台回传 `status = "timeout"`
- Skill 必须进入 `onCancelAction`

## 11.4 错误

当平台无法完成上传、选择或确认时：

- 平台回传 `status = "error"`
- Skill 必须进入 `onCancelAction`

硬规则：

- Skill 不得假设 `status = "ok"` 是唯一分支
- 没有 `fallback_cancel` 的 Skill 不可上线

---

## 12. Driver 骨架：唤醒与降级代码范例

以下示例展示一个极简的 `runtime/driver.py`，演示如何：

- 从 `stdin` 接收平台注入的 `action`、`status`、`result`
- 安全提取 `files` 或 `selectedIds`
- 输出 `dashboard.patch`
- 执行真实 Python 业务逻辑
- 处理 `action == "fallback_cancel"` 的硬规则兜底

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
STATE_FILE = RUNTIME_DIR / "ui_state.json"


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"current_step": "step1"}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"current_step": "step1"}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def emit(envelope: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_patch(summary: str, next_step: str) -> None:
    emit(
        {
            "threadId": "thread-runtime",
            "skillName": "demo_skill",
            "skillRunId": "run-demo-001",
            "event": "dashboard.patch",
            "docId": "dashboard:demo-skill",
            "payload": {
                "docId": "dashboard:demo-skill",
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/demo_skill/data/dashboard.json",
                "ops": [
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "summary-text"},
                        "value": {
                            "id": "summary-text",
                            "type": "Text",
                            "content": summary,
                        },
                    },
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "stepper-main"},
                        "value": {
                            "id": "stepper-main",
                            "type": "Stepper",
                            "steps": [
                                {"id": "step1", "title": "上传底表", "status": "completed"},
                                {"id": "step2", "title": next_step, "status": "active"},
                            ],
                        },
                    },
                ],
            },
        },
    )


def request_upload() -> None:
    emit(
        {
            "threadId": "thread-runtime",
            "skillName": "demo_skill",
            "skillRunId": "run-demo-001",
            "event": "hitl.file_request",
            "payload": {
                "requestId": "req-upload-step1",
                "title": "请上传底表文件",
                "accept": ".xlsx",
                "mount": "workspace://demo-skill/input",
                "multiple": True,
                "resumeAction": "resume_after_upload",
                "onCancelAction": "fallback_cancel",
            },
        },
    )


def request_choice() -> None:
    emit(
        {
            "threadId": "thread-runtime",
            "skillName": "demo_skill",
            "skillRunId": "run-demo-001",
            "event": "hitl.choice_request",
            "payload": {
                "requestId": "req-choice-output",
                "title": "请选择输出格式",
                "mode": "single",
                "options": [
                    {"id": "html", "label": "生成 HTML"},
                    {"id": "md", "label": "生成 Markdown"},
                    {"id": "other", "label": "生成其他"},
                ],
                "resumeAction": "resume_after_choice",
                "onCancelAction": "fallback_cancel",
            },
        },
    )


def run_python_business(files: list[dict[str, Any]], selected_ids: list[str]) -> str:
    file_count = len(files)
    output_mode = selected_ids[0] if selected_ids else "unknown"
    return f"业务执行完成：收到 {file_count} 个逻辑文件，输出模式为 {output_mode}。"


def main() -> int:
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}

    action = str(payload.get("action") or "").strip()
    status = str(payload.get("status") or "").strip()
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}

    state = load_state()

    if action == "start":
        request_upload()
        return 0

    if action == "fallback_cancel":
        state["current_step"] = "cancelled"
        save_state(state)
        emit_patch("用户取消、超时或平台错误。流程已安全降级并终止。", "流程已终止")
        return 0

    if action == "resume_after_upload":
        if status != "ok":
            payload["action"] = "fallback_cancel"
            return main_from_payload(payload)

        files = result.get("files") if isinstance(result.get("files"), list) else []
        safe_files = []
        for item in files:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("uri") or "").strip()
            name = str(item.get("name") or "").strip()
            if not uri.startswith("workspace://"):
                continue
            safe_files.append({"name": name, "uri": uri})

        if not safe_files:
            payload["action"] = "fallback_cancel"
            return main_from_payload(payload)

        state["uploaded_files"] = safe_files
        state["current_step"] = "choice"
        save_state(state)
        emit_patch("底表上传完成，进入输出格式选择。", "选择输出格式")
        request_choice()
        return 0

    if action == "resume_after_choice":
        if status != "ok":
            payload["action"] = "fallback_cancel"
            return main_from_payload(payload)

        selected_ids = result.get("selectedIds") if isinstance(result.get("selectedIds"), list) else []
        safe_selected_ids = [str(item).strip() for item in selected_ids if str(item).strip()]

        if not safe_selected_ids:
            payload["action"] = "fallback_cancel"
            return main_from_payload(payload)

        files = state.get("uploaded_files") if isinstance(state.get("uploaded_files"), list) else []
        summary = run_python_business(files, safe_selected_ids)
        state["current_step"] = "done"
        state["selected_ids"] = safe_selected_ids
        save_state(state)
        emit_patch(summary, "流程已完成")
        return 0

    payload["action"] = "fallback_cancel"
    return main_from_payload(payload)


def main_from_payload(payload: dict[str, Any]) -> int:
    backup_stdin = sys.stdin
    try:
        from io import StringIO

        sys.stdin = StringIO(json.dumps(payload, ensure_ascii=False))
        return main()
    finally:
        sys.stdin = backup_stdin


if __name__ == "__main__":
    raise SystemExit(main())
```

### 示例说明

该示例体现以下硬规则：

- Skill 从 `stdin` 读取恢复参数
- 只信任逻辑 URI，不信任物理路径
- `status != "ok"` 立即走 `fallback_cancel`
- 业务逻辑由 Skill 自己执行
- 平台只负责恢复，不负责解释 `files` 或 `selectedIds`

---

## 13. 开发者自检清单

上线前，Skill 开发者必须确认：

- 是否所有步骤都有明确 `action`
- 是否所有 `hitl.*` 都填写了 `requestId`
- 是否所有 `hitl.*` 都填写了 `resumeAction`
- 是否所有 `hitl.*` 都填写了 `onCancelAction`
- 是否所有恢复分支都处理了 `cancel/timeout/error`
- 是否彻底避免了物理路径泄漏
- 是否将中间态落盘到 Skill 自有 runtime 目录
- 是否确保平台不包含业务 if/else

任一项为否，禁止上线。

---

## 14. 禁止事项

以下实现一律禁止：

- 在平台 Python flow 中判断业务缺件
- 在平台前端中推断业务下一步
- 在协议中传递物理磁盘路径
- 在 EmbeddedWeb 中直接调用平台私有业务函数
- 依赖浏览器内存保存唯一业务状态
- 不处理 `cancel/timeout/error`
- 让平台替业务拼 dashboard 摘要与指标

---

## 15. 最终裁决

Skill-First 不是“平台帮业务做了一半，Skill 再补另一半”。

Skill-First 的唯一合法实现是：

- 平台提供通用运行时
- 平台提供盲转发
- 平台提供容器
- Skill 拥有全部业务主权

如果一个 Skill 离开平台业务 if/else 就无法运行，它就不是 Skill-First。它只是把旧式流程编排换了一个名字。
