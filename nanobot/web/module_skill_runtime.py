"""统一模块 Skill 运行时：按 module.json + flow 驱动大盘 Patch 与 HITL ChatCard。

业务团队在 ``<skills_root>/<module_id>/`` 下交付 ``module.json``、``SKILL.md``、``data/dashboard.json``；
模型通过工具 ``module_skill_runtime`` 或 Fast-path ``chat_card_intent`` 调用本模块。
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from nanobot.agent.loop import get_current_thread_id
from nanobot.web.mission_control import MissionControlManager
from nanobot.web.skill_ui_patch import SkillUiPatchPusher
from nanobot.web.skills import get_skills_root

# (thread_id, module_id) -> 跨 HITL 步骤的合并状态（样本级；生产可换 Redis）
_SESSION: dict[tuple[str, str], dict[str, Any]] = {}


def _session_key(thread_id: str, module_id: str) -> tuple[str, str]:
    return (thread_id.strip(), module_id.strip())


def merge_module_session(thread_id: str, module_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    key = _session_key(thread_id, module_id)
    cur = _SESSION.setdefault(key, {})
    cur.update({k: v for k, v in patch.items() if v is not None})
    return cur


def clear_module_session(thread_id: str, module_id: str) -> None:
    _SESSION.pop(_session_key(thread_id, module_id), None)


def load_module_config(module_id: str) -> dict[str, Any]:
    root = get_skills_root()
    path = root / module_id.strip() / "module.json"
    if not path.is_file():
        raise FileNotFoundError(f"module.json missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("module.json must be a JSON object")
    return raw


def synthetic_path_for_data_file(data_file: str) -> str:
    """构建与前端 SduiView 一致的 syntheticPath（dataFile 为 workspace 相对片段）。"""
    df = (data_file or "").strip()
    if not df:
        raise ValueError("dataFile is empty")
    return f"skill-ui://SduiView?dataFile={df}"


def _pusher_for(cfg: dict[str, Any]) -> SkillUiPatchPusher:
    doc_id = str(cfg.get("docId") or "").strip()
    data_file = str(cfg.get("dataFile") or "").strip()
    if not doc_id or not data_file:
        raise ValueError("module.json requires docId and dataFile")
    return SkillUiPatchPusher(synthetic_path_for_data_file(data_file), doc_id=doc_id)


# ── demo_compliance 流程（标准样本）────────────────────────────────────────


async def _flow_demo_compliance(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    pusher = _pusher_for(cfg)
    doc_id = str(cfg["docId"])
    sp = synthetic_path_for_data_file(str(cfg["dataFile"]))
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await pusher.update_node(
            "stepper-main",
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "waiting",
                     "detail": [{"title": "等待启动…", "status": "waiting"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "waiting",
                     "detail": [{"title": "等待用户确认", "status": "waiting"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "waiting",
                     "detail": [{"title": "等待上传", "status": "waiting"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await mc.emit_guidance(
            context=(
                "【安全合规检查】模块已就绪。\n"
                "流程：初始化 → 选择标准 → 上传材料 → 生成报告。\n"
                "点击下方按钮启动，或由助手调用 module_skill_runtime(action=\"start\")。"
            ),
            actions=[
                {
                    "label": "启动安全检查",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "start", "state": {}},
                },
                {
                    "label": "取消",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "cancel", "state": {}},
                },
            ],
        )
        return {"ok": True, "next": "start"}

    if action == "start":
        await pusher.update_node(
            "stepper-main",
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "running",
                     "detail": [{"title": "正在扫描配置项…", "status": "running"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "waiting",
                     "detail": [{"title": "等待用户确认", "status": "waiting"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "waiting",
                     "detail": [{"title": "等待上传", "status": "waiting"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await pusher.update_nodes([
            ("stat-total", "Statistic", {"value": "42"}),
            ("stat-passed", "Statistic", {"value": "0", "color": "success"}),
            ("stat-failed", "Statistic", {"value": "0", "color": "danger"}),
            ("stat-progress", "Statistic", {"value": "10%"}),
        ])
        return {"ok": True, "next": "choose_standard"}

    if action == "choose_standard":
        await pusher.update_node(
            "stepper-main",
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "running",
                     "detail": [{"title": "等待用户选择", "status": "running"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "waiting",
                     "detail": [{"title": "等待上传", "status": "waiting"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await pusher.update_node("stat-progress", "Statistic", {"value": "25%"})
        await mc.emit_choices(
            title="请选择本次合规检查所依据的标准：",
            options=[
                {"id": "iso27001", "label": "ISO 27001（信息安全管理）"},
                {"id": "gdpr", "label": "GDPR（数据隐私保护）"},
                {"id": "pci_dss", "label": "PCI DSS（支付卡行业安全）"},
                {"id": "gb_t22080", "label": "GB/T 22080（国家标准）"},
            ],
            module_id=module_id,
            next_action="upload_material",
        )
        return {"ok": True, "next": "upload_material"}

    if action == "upload_material":
        standard = str(sess.get("standard") or state.get("standard") or "未指定")
        merge_module_session(thread_id, module_id, {"standard": standard})
        await pusher.update_node(
            "stepper-main",
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "done",
                     "detail": [{"title": f"已选：{standard}", "status": "done"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "running",
                     "detail": [{"title": "等待上传授权声明书", "status": "running"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await pusher.update_node("stat-progress", "Statistic", {"value": "50%"})
        await mc.ask_for_file(
            purpose="compliance_docs",
            title=f"请上传【{standard}】所需的授权声明书（PDF/Word）",
            accept=".pdf,.doc,.docx",
            multiple=False,
            module_id=module_id,
            next_action="after_upload",
        )
        return {"ok": True, "next": "after_upload"}

    if action == "after_upload":
        merged = merge_module_session(thread_id, module_id, dict(state))
        up = merged.get("upload") if isinstance(merged.get("upload"), dict) else {}
        name = str(up.get("name") or "文件")
        cid = str(merged.get("cardId") or state.get("cardId") or "").strip()
        if cid:
            await mc.replace_card(
                card_id=cid,
                title="文件已收到",
                node={
                    "type": "Card",
                    "title": f"已收到：{name}",
                    "density": "compact",
                    "children": [
                        {
                            "type": "Text",
                            "content": "材料已记录。请让助手执行 module_skill_runtime(action=\"finish\") 生成报告。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        std = str(merged.get("standard") or "")
        await pusher.update_node(
            "stepper-main",
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "done",
                     "detail": [{"title": f"已选：{std or '—'}", "status": "done"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "done",
                     "detail": [{"title": "授权声明书已接收", "status": "done"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "running",
                     "detail": [{"title": "等待生成", "status": "running"}]},
                ]
            },
        )
        await pusher.update_node("stat-progress", "Statistic", {"value": "75%"})
        return {"ok": True, "next": "finish", "hint": "调用 action=finish 完成大盘与产物"}

    if action == "finish":
        standard = str(sess.get("standard") or state.get("standard") or "合规标准")
        passed = int(state.get("passed", 38))
        failed = int(state.get("failed", 4))
        await pusher.update_node(
            "stepper-main",
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "done",
                     "detail": [{"title": f"已选：{standard}", "status": "done"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "done",
                     "detail": [{"title": "授权声明书已接收", "status": "done"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "done",
                     "detail": [{"title": "报告已生成", "status": "done"}]},
                ]
            },
        )
        await pusher.update_nodes([
            ("stat-passed", "Statistic", {"value": str(passed), "color": "success"}),
            ("stat-failed", "Statistic", {"value": str(failed), "color": "danger"}),
            ("stat-progress", "Statistic", {"value": "100%", "color": "success"}),
        ])
        out_path = f"workspace/skills/{module_id}/output/compliance_report.pdf"
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="compliance-report-001",
            label=f"{standard} 合规检查报告.pdf",
            path=out_path,
            kind="pdf",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {
            "ok": True,
            "done": True,
            "summary": f"检查完成：{passed} 项通过，{failed} 项风险，报告已生成。",
        }

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def run_module_action(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any] | None,
    thread_id: str | None,
    docman: Any = None,
) -> dict[str, Any]:
    tid = (thread_id or get_current_thread_id() or "").strip()
    if not tid:
        return {"ok": False, "error": "thread_id missing (not in web chat context)"}
    mid = (module_id or "").strip()
    act = (action or "").strip()
    if not mid or not act:
        return {"ok": False, "error": "module_id and action are required"}
    try:
        cfg = load_module_config(mid)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.warning("module_skill_runtime load failed | module={} | {}", mid, e)
        return {"ok": False, "error": str(e)}
    flow = str(cfg.get("flow") or "demo_compliance")
    st = dict(state or {})
    if flow == "demo_compliance":
        return await _flow_demo_compliance(
            module_id=mid,
            action=act,
            state=st,
            thread_id=tid,
            docman=docman,
            cfg=cfg,
        )
    return {"ok": False, "error": f"unsupported flow: {flow!r}"}


def parse_module_action_payload(payload: Any) -> tuple[str, str, dict[str, Any]] | None:
    """从 chat_card_intent / module_action 的 payload 解析 (module_id, action, state)。"""
    if not isinstance(payload, dict):
        return None
    mid = str(payload.get("moduleId") or "").strip()
    act = str(payload.get("action") or "").strip()
    raw_state = payload.get("state")
    st: dict[str, Any] = dict(raw_state) if isinstance(raw_state, dict) else {}
    if not mid or not act:
        return None
    return mid, act, st


async def dispatch_chat_card_intent(
    intent: dict[str, Any] | None,
    *,
    thread_id: str,
    docman: Any = None,
) -> tuple[bool, str]:
    """解析会话内 HITL 的 ``chat_card_intent``；若已消费则返回 (True, RunFinished.message)。"""
    if not intent:
        return False, ""
    verb = str(intent.get("verb") or "")
    card_id = str(intent.get("cardId") or "").strip()
    payload = intent.get("payload")

    if verb == "module_action":
        parsed = parse_module_action_payload(payload)
        if not parsed:
            return True, json.dumps({"ok": False, "error": "invalid module_action payload"}, ensure_ascii=False)
        mid, act, st = parsed
        if card_id:
            st = {**st, "cardId": card_id}
        result = await run_module_action(
            module_id=mid, action=act, state=st, thread_id=thread_id, docman=docman
        )
        return True, json.dumps(result, ensure_ascii=False)

    if verb == "choice_selected" and isinstance(payload, dict):
        mid = str(payload.get("moduleId") or "").strip()
        na = str(payload.get("nextAction") or "").strip()
        opt = payload.get("optionId")
        if mid and na and opt is not None:
            st: dict[str, Any] = {"standard": str(opt)}
            if card_id:
                st["cardId"] = card_id
            result = await run_module_action(
                module_id=mid, action=na, state=st, thread_id=thread_id, docman=docman
            )
            return True, json.dumps(result, ensure_ascii=False)

    return False, ""
