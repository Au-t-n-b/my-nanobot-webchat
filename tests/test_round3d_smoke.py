"""Round 3D smoke test — 7 paths end-to-end, real store + mock LLM."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.skill_change_store import SkillChangeStore, build_similarity_key
from nanobot.agent.tools.skill_manage import SkillManageTool


def _write_skill(skills_dir: Path, name: str, description: str, body: str = "") -> None:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n\n{body or 'Body text.'}"
    (d / "SKILL.md").write_text(content, encoding="utf-8")


def _mock_provider(response_json: dict):
    provider = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps(response_json, ensure_ascii=False)
    async def _chat(*a, **kw):
        return resp
    provider.chat = _chat
    return provider


@pytest.fixture
def ws(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    return tmp_path


@pytest.fixture
def store(ws: Path):
    return SkillChangeStore(workspace=ws, expiry_days=60)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 1: existing_covered — 已有 skill 完全覆盖 → 不创建 pending
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_path1_existing_covered(ws: Path, store: SkillChangeStore):
    skills_dir = ws / "skills"
    _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用到生产集群",
                 "## When to use\n\n部署 K8s 时使用。\n## Rules\n\n- 规则1")

    before = store.pending_count()
    req = store.create_request(
        action="create",
        skill_name="k8s-deploy-v2",
        reason="部署 K8s 应用到集群",
        proposed_content="---\nname: k8s-deploy-v2\ndescription: 部署 K8s\n---\nBody",
        coverage_result={
            "decision": "existing_covered",
            "confidence": 0.92,
            "skill_name": "k8s-deploy",
            "reason_zh": "已有技能已覆盖 K8s 部署场景",
        },
    )

    assert req.status == "covered_by_existing"
    assert store.pending_count() == before, "covered_by_existing must NOT insert into DB"
    ids = json.loads(req.related_existing_skill_ids or "[]")
    assert "k8s-deploy" in ids
    print(f"[PASS] Path 1: existing_covered → status={req.status}, pending_count unchanged={before}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 2: existing_related — 已有 skill 相关但不完全覆盖 → 创建 pending + 警告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_path2_existing_related(ws: Path, store: SkillChangeStore):
    skills_dir = ws / "skills"
    _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用",
                 "## When to use\n\n部署时使用。")

    req = store.create_request(
        action="create",
        skill_name="k8s-monitor",
        reason="K8s 集群监控配置",
        proposed_content="---\nname: k8s-monitor\ndescription: K8s 监控\n---\nBody",
        coverage_result={
            "decision": "existing_related_but_distinct",
            "confidence": 0.78,
            "skill_name": "k8s-deploy",
            "reason_zh": "部署技能相关但候选侧重监控",
        },
    )

    assert req.status == "pending"
    assert req.existing_coverage_status == "related_existing"
    ids = json.loads(req.related_existing_skill_ids or "[]")
    assert "k8s-deploy" in ids
    assert req.related_existing_skill_note is not None
    assert store.pending_count() == 1
    print(f"[PASS] Path 2: existing_related → status={req.status}, "
          f"coverage={req.existing_coverage_status}, related={ids}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 3: normal create — 无已有 skill、无 coverage → 正常 pending
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_path3_normal_create(ws: Path, store: SkillChangeStore):
    req = store.create_request(
        action="create",
        skill_name="terraform-aws",
        reason="Terraform AWS 基础设施部署",
        proposed_content="---\nname: terraform-aws\ndescription: Terraform AWS\n---\nBody",
    )

    assert req.status == "pending"
    assert req.existing_coverage_status is None
    assert req.related_existing_skill_ids is None
    assert store.pending_count() == 1
    print(f"[PASS] Path 3: normal create → status={req.status}, id={req.id}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 4: pending duplicate — same_duplicate 合并到已有 pending
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_path4_pending_duplicate(ws: Path, store: SkillChangeStore):
    # 先创建第一个 pending
    first = store.create_request(
        action="create",
        skill_name="ci-setup",
        reason="CI 流水线搭建",
        proposed_content="---\nname: ci-setup\ndescription: CI\n---\nBody1",
    )
    assert first.status == "pending"
    assert store.pending_count() == 1

    # 第二个请求被 judge 判定为 same_duplicate
    second = store.create_request(
        action="create",
        skill_name="ci-setup",
        reason="CI 配置",
        proposed_content="---\nname: ci-setup\ndescription: CI v2\n---\nBody2",
        judge_result={
            "decision": "same_duplicate",
            "confidence": 0.95,
            "target_id": first.id,
            "reason_zh": "语义相同",
        },
    )

    assert second.status == "merged_with_existing"
    assert second.duplicate_count == 1
    assert store.pending_count() == 1, "merge 不应增加 pending_count"

    # 验证 cross-action 不合并
    third = store.create_request(
        action="edit",
        skill_name="ci-setup",
        reason="编辑 CI",
        proposed_content="---\nname: ci-setup\ndescription: CI v3\n---\nBody3",
        judge_result={
            "decision": "same_duplicate",
            "confidence": 0.95,
            "target_id": first.id,
            "reason_zh": "不同 action",
        },
    )
    assert third.status == "pending", "cross-action 不应自动合并"
    assert store.pending_count() == 2
    print(f"[PASS] Path 4: pending duplicate → merged_count={second.duplicate_count}, "
          f"cross-action correctly fell back to pending")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 5: blacklist — blacklist_hit 阻止创建
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_path5_blacklist(ws: Path, store: SkillChangeStore):
    before = store.pending_count()

    req = store.create_request(
        action="create",
        skill_name="spam-skill",
        reason="垃圾内容",
        proposed_content="---\nname: spam-skill\ndescription: spam\n---\nBody",
        judge_result={
            "decision": "blacklist_hit",
            "confidence": 0.95,
            "target_id": None,
            "reason_zh": "命中黑名单",
        },
    )

    assert req.status == "blocked_by_blacklist"
    assert store.pending_count() == before, "blacklist 不应插入 DB"

    # 验证 blacklist 优先于 covered_by_existing
    covered_req = store.create_request(
        action="create",
        skill_name="spam-skill",
        reason="垃圾内容",
        proposed_content="---\nname: spam-skill\ndescription: spam\n---\nBody",
        judge_result={
            "decision": "blacklist_hit",
            "confidence": 0.95,
            "target_id": None,
            "reason_zh": "命中黑名单",
        },
        coverage_result={
            "decision": "no_existing_match",
            "confidence": 0.90,
            "skill_name": None,
            "reason_zh": "无匹配",
        },
    )
    assert covered_req.status == "blocked_by_blacklist", "blacklist 必须优先于 coverage"
    print(f"[PASS] Path 5: blacklist → status={req.status}, priority over coverage confirmed")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 6: generate-enhanced — 两阶段 LLM pipeline → 新 pending
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_path6_generate_enhanced(ws: Path, store: SkillChangeStore):
    # 创建 canonical pending + 一个 duplicate event
    canonical = store.create_request(
        action="create",
        skill_name="docker-build",
        reason="Docker 镜像构建",
        proposed_content="---\nname: docker-build\ndescription: Docker 构建\n---\n\n## When to use\n\n构建镜像。\n\n## Rules\n\n- 规则1",
    )
    assert canonical.status == "pending"

    # 模拟 same_duplicate → 会创建 duplicate event
    merged = store.create_request(
        action="create",
        skill_name="docker-build",
        reason="Docker 镜像构建推送到 ECR",
        proposed_content="---\nname: docker-build\ndescription: Docker ECR\n---\nBody2",
        judge_result={
            "decision": "same_duplicate",
            "confidence": 0.93,
            "target_id": canonical.id,
            "reason_zh": "Docker 构建相关",
        },
    )
    assert merged.status == "merged_with_existing"

    # 获取 duplicate events
    events = store.list_duplicate_events(canonical.id)
    assert len(events) == 1, f"应有 1 个 duplicate event，实际 {len(events)}"
    event_id = events[0].id

    # mock provider: brief 阶段返回 should_generate=true, generate 阶段返回完整 SKILL.md
    brief_provider = MagicMock()
    brief_resp = MagicMock()
    brief_resp.content = json.dumps({
        "absorbed_points": [{"type": "rule", "point_zh": "推送到 ECR", "source": "dup:" + event_id}],
        "ignored_points": [],
        "conflicts": [],
        "skill_shape": {"name": "docker-build", "description_zh": "Docker 构建",
                        "use_when": ["构建镜像"], "do_not_use_when": ["一次性任务"]},
        "should_generate_enhanced": True,
        "summary_zh": "ECR 推送有新增价值",
    })
    brief_provider.chat = AsyncMock(return_value=brief_resp)

    generate_provider = MagicMock()
    generate_resp = MagicMock()
    generate_resp.content = (
        "---\nname: docker-build\ndescription: Docker 镜像构建并推送到 ECR\n---\n\n"
        "## When to use\n\n构建 Docker 镜像并推送时使用。\n\n## Rules\n\n- 推送到 ECR\n"
        "---change_summary---\n"
        '{"preserved_points": [], "added_points": ["推送到 ECR"], "changed_points": [], "ignored_points": []}\n'
        "---end_change_summary---"
    )
    generate_provider.chat = AsyncMock(return_value=generate_resp)

    # 两次调用分别返回不同 provider（brief → generate）
    call_count = 0
    original_set = store.set_provider

    def _switch_provider(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            store._provider = brief_provider
        else:
            store._provider = generate_provider

    # 直接设为 brief provider
    store._provider = brief_provider
    store._model = "test"

    # 第二次调 generate 时需要切换 provider
    original_chat = store._call_llm_merge_generate_async

    # 在 brief 返回后、generate 调用前切换 provider
    import types

    async def _gen_with_switch(*a, **kw):
        store._provider = generate_provider
        return await original_chat(*a, **kw)

    store._call_llm_merge_generate_async = _gen_with_switch

    result = await store.generate_enhanced_candidate(
        target_request_id=canonical.id,
        selected_event_ids=[event_id],
        other_extra="",
    )

    assert result["status"] == "pending_review", f"期望 pending_review，实际 {result}"
    assert "request_id" in result

    # 验证新的 enhanced pending 被创建
    enhanced = store.get_request(result["request_id"])
    assert enhanced is not None
    assert enhanced.status == "pending"
    assert "增强版候选" in (enhanced.reason or "")
    print(f"[PASS] Path 6: generate-enhanced → status={result['status']}, "
          f"enhanced_id={result['request_id']}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Path 7: Hermes create-only guard — SkillManageTool schema + runtime
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_path7_hermes_create_only_guard(ws: Path, store: SkillChangeStore):
    hermes_tool = SkillManageTool(
        workspace=ws,
        change_store=store,
        trigger_conversation="test evidence",
        allowed_actions={"create"},
    )
    main_tool = SkillManageTool(
        workspace=ws,
        change_store=store,
    )

    # Hermes schema: 只有 create
    hermes_enum = hermes_tool.parameters["properties"]["action"]["enum"]
    assert hermes_enum == ["create"], f"Hermes enum 应为 ['create']，实际 {hermes_enum}"

    # 主 agent schema: 四种 action
    main_enum = main_tool.parameters["properties"]["action"]["enum"]
    assert set(main_enum) == {"create", "edit", "patch", "delete"}

    # Hermes runtime: create 允许
    r = await hermes_tool.execute(
        action="create", name="test-ok", reason="test",
        content="---\nname: test-ok\ndescription: test\n---\nBody",
    )
    assert r["success"] is True

    # Hermes runtime: patch 被拒
    r = await hermes_tool.execute(action="patch", name="test-ok", reason="test", old_string="x", new_string="y")
    assert r["success"] is False
    assert "not allowed" in r["error"].lower()

    # Hermes runtime: edit 被拒
    r = await hermes_tool.execute(
        action="edit", name="test-ok", reason="test",
        content="---\nname: test-ok\ndescription: test\n---\nBody2",
    )
    assert r["success"] is False
    assert "not allowed" in r["error"].lower()

    # Hermes runtime: delete 被拒
    r = await hermes_tool.execute(action="delete", name="test-ok", reason="test")
    assert r["success"] is False
    assert "not allowed" in r["error"].lower()

    # 主 agent: create 正常
    r = await main_tool.execute(
        action="create", name="main-test", reason="test",
        content="---\nname: main-test\ndescription: test\n---\nBody",
    )
    assert r["success"] is True

    print(f"[PASS] Path 7: Hermes create-only guard → "
          f"schema={hermes_enum}, "
          f"create=ok, patch=blocked, edit=blocked, delete=blocked, "
          f"main_agent schema={set(main_enum)}")
