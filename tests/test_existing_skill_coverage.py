"""P0.5 tests: Existing skill coverage check — summary, prefilter, judge, integration."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nanobot.agent.skill_change_store import (
    ExistingSkillSummary,
    SkillChangeStore,
    SkillChangeRequest,
    build_similarity_key,
    list_existing_skill_summaries,
    normalize_text_for_similarity,
    similarity_score,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(workspace=tmp_path, expiry_days=60)


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    sd = tmp_path / "skills"
    sd.mkdir()
    return sd


def _write_skill(skills_dir: Path, name: str, description: str = "测试技能", body_extra: str = "") -> Path:
    """Helper: create a skill directory with SKILL.md."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n"
    content += f"## When to use\n\n当需要{description}时使用。\n\n"
    content += f"## Rules\n\n- 规则1\n- 规则2\n\n"
    if body_extra:
        content += body_extra + "\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def _mock_provider(response_json: dict):
    """Create a mock LLM provider that returns given JSON."""
    provider = MagicMock()
    resp = MagicMock()
    resp.content = json.dumps(response_json, ensure_ascii=False)
    async def _chat(*args, **kwargs):
        return resp
    provider.chat = _chat
    return provider


# ── Test: ExistingSkillSummary ────────────────────────────────────────────────


class TestExistingSkillSummary:
    """Test scanning and parsing of existing approved skills."""

    def test_reads_frontmatter(self, skills_dir: Path):
        _write_skill(skills_dir, "my-skill", "部署 K8s 应用")
        summaries = list_existing_skill_summaries(skills_dir)
        assert len(summaries) == 1
        assert summaries[0].skill_name == "my-skill"
        assert "部署" in summaries[0].description or "K8s" in summaries[0].description

    def test_skips_invalid_skill(self, skills_dir: Path):
        """A directory without valid SKILL.md should be skipped."""
        bad_dir = skills_dir / "bad-skill"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("not valid frontmatter", encoding="utf-8")
        # Should not crash
        summaries = list_existing_skill_summaries(skills_dir)
        assert len(summaries) == 1
        assert summaries[0].skill_name == "bad-skill"
        # description should be empty since no frontmatter
        assert summaries[0].description == ""

    def test_includes_description_and_excerpt(self, skills_dir: Path):
        _write_skill(skills_dir, "deploy-app", "部署应用到 K8s 集群")
        summaries = list_existing_skill_summaries(skills_dir)
        assert len(summaries) == 1
        assert "部署" in summaries[0].description
        assert len(summaries[0].content_excerpt) > 0

    def test_hash_changes_when_file_changes(self, skills_dir: Path):
        _write_skill(skills_dir, "my-skill", "测试")
        summaries1 = list_existing_skill_summaries(skills_dir)
        hash1 = summaries1[0].file_hash
        # Modify the file
        (skills_dir / "my-skill" / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: 修改后的测试\n---\n新内容", encoding="utf-8"
        )
        summaries2 = list_existing_skill_summaries(skills_dir)
        hash2 = summaries2[0].file_hash
        assert hash1 != hash2

    def test_chinese_similarity_key(self, skills_dir: Path):
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用到生产集群")
        summaries = list_existing_skill_summaries(skills_dir)
        assert len(summaries) == 1
        sk = summaries[0].similarity_key
        # Similarity key should contain normalized parts
        assert "k8s-deploy" in sk.lower() or "create" in sk.lower()

    def test_extracts_when_to_use(self, skills_dir: Path):
        _write_skill(skills_dir, "test-skill", "测试技能")
        summaries = list_existing_skill_summaries(skills_dir)
        assert len(summaries) == 1
        assert "当需要" in summaries[0].when_to_use

    def test_empty_skills_dir(self, skills_dir: Path):
        summaries = list_existing_skill_summaries(skills_dir)
        assert summaries == []

    def test_no_skills_dir(self, tmp_path: Path):
        summaries = list_existing_skill_summaries(tmp_path / "nonexistent")
        assert summaries == []


# ── Test: Existing skill prefilter ───────────────────────────────────────────


class TestExistingSkillPrefilter:
    """Test n-gram based prefiltering against existing skills."""

    def test_exact_name_match(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用")
        sim_key = build_similarity_key("create", "k8s-deploy", "部署 K8s")
        results = store._prefilter_existing_skills(sim_key, "k8s-deploy")
        assert len(results) >= 1
        assert results[0].skill_name == "k8s-deploy"

    def test_chinese_similarity(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "docker-build", "使用 Docker 构建镜像并推送到 ECR")
        sim_key = build_similarity_key("create", "docker-ecr", "使用 Docker 构建并推送镜像到 ECR 仓库")
        results = store._prefilter_existing_skills(sim_key, "docker-ecr")
        # Should find the existing skill via n-gram similarity
        assert len(results) >= 1

    def test_limits_top_5(self, store: SkillChangeStore, skills_dir: Path):
        for i in range(10):
            _write_skill(skills_dir, f"skill-{i:02d}", f"技能 {i} 的描述信息，包含 Docker 构建")
        sim_key = build_similarity_key("create", "new-skill", "Docker 构建相关任务")
        results = store._prefilter_existing_skills(sim_key, "new-skill")
        assert len(results) <= 5

    def test_ignores_low_similarity(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "python-testing", "Python 单元测试最佳实践")
        # Search for something completely unrelated
        sim_key = build_similarity_key("create", "terraform-aws", "使用 Terraform 部署 AWS 基础设施")
        results = store._prefilter_existing_skills(sim_key, "terraform-aws")
        # Should not match
        assert not any(r.skill_name == "python-testing" for r in results)


# ── Test: LLM coverage judge ────────────────────────────────────────────────


class TestExistingCoverageJudge:
    """Test the LLM-based existing skill coverage judge."""

    @pytest.mark.asyncio
    async def test_covered_blocks_creation(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用到生产集群")
        provider = _mock_provider({
            "decision": "existing_covered",
            "confidence": 0.92,
            "skill_name": "k8s-deploy",
            "reason_zh": "已有技能已覆盖 K8s 部署场景",
        })
        store.set_provider(provider, "test")
        sim_key = build_similarity_key("create", "k8s-deploy-v2", "部署 K8s 应用到集群")
        existing = store._prefilter_existing_skills(sim_key, "k8s-deploy-v2")
        result = await store._call_llm_coverage_judge_async(
            action="create", skill_name="k8s-deploy-v2", reason="部署 K8s 应用",
            description="部署 K8s 应用", trigger_conversation="", existing_candidates=existing,
        )
        assert result is not None
        assert result["decision"] == "existing_covered"
        assert result["confidence"] >= 0.85

    @pytest.mark.asyncio
    async def test_related_allows_pending_with_warning(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用")
        provider = _mock_provider({
            "decision": "existing_related_but_distinct",
            "confidence": 0.78,
            "skill_name": "k8s-deploy",
            "reason_zh": "已有部署技能相关，但候选侧重监控场景",
        })
        store.set_provider(provider, "test")
        sim_key = build_similarity_key("create", "k8s-monitor", "K8s 集群监控配置")
        existing = store._prefilter_existing_skills(sim_key, "k8s-monitor")
        result = await store._call_llm_coverage_judge_async(
            action="create", skill_name="k8s-monitor", reason="K8s 监控",
            description="K8s 监控配置", trigger_conversation="", existing_candidates=existing,
        )
        assert result is not None
        assert result["decision"] == "existing_related_but_distinct"

    @pytest.mark.asyncio
    async def test_no_match_allows_pending(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "python-test", "Python 测试框架")
        provider = _mock_provider({
            "decision": "no_existing_match",
            "confidence": 0.90,
            "skill_name": None,
            "reason_zh": "无已有技能匹配",
        })
        store.set_provider(provider, "test")
        sim_key = build_similarity_key("create", "terraform-aws", "Terraform AWS 部署")
        existing = store._prefilter_existing_skills(sim_key, "terraform-aws")
        result = await store._call_llm_coverage_judge_async(
            action="create", skill_name="terraform-aws", reason="Terraform AWS",
            description="Terraform AWS 部署", trigger_conversation="", existing_candidates=existing,
        )
        assert result is not None
        assert result["decision"] == "no_existing_match"

    @pytest.mark.asyncio
    async def test_invalid_json_fallback_normal_pending(self, store: SkillChangeStore, skills_dir: Path):
        """Invalid JSON from LLM should return None (fallback to normal pending)."""
        _write_skill(skills_dir, "test-skill", "测试技能")
        provider = MagicMock()
        resp = MagicMock()
        resp.content = "This is not JSON at all"
        async def _chat(*a, **kw):
            return resp
        provider.chat = _chat
        store.set_provider(provider, "test")
        sim_key = build_similarity_key("create", "test-skill-v2", "测试技能 v2")
        existing = store._prefilter_existing_skills(sim_key, "test-skill-v2")
        result = await store._call_llm_coverage_judge_async(
            action="create", skill_name="test-skill-v2", reason="测试",
            description="测试技能 v2", trigger_conversation="", existing_candidates=existing,
        )
        assert result is None  # fallback

    @pytest.mark.asyncio
    async def test_invalid_decision_fallback(self, store: SkillChangeStore, skills_dir: Path):
        """Invalid decision enum should return None."""
        _write_skill(skills_dir, "test-skill", "测试技能")
        provider = _mock_provider({
            "decision": "invalid_decision",
            "confidence": 0.90,
            "skill_name": "test-skill",
            "reason_zh": "无效决策",
        })
        store.set_provider(provider, "test")
        sim_key = build_similarity_key("create", "test-skill-v2", "测试技能 v2")
        existing = store._prefilter_existing_skills(sim_key, "test-skill-v2")
        result = await store._call_llm_coverage_judge_async(
            action="create", skill_name="test-skill-v2", reason="测试",
            description="测试技能 v2", trigger_conversation="", existing_candidates=existing,
        )
        assert result is None  # fallback


# ── Test: create_request integration ─────────────────────────────────────────


class TestCreateRequestCoverageIntegration:
    """Test the full create_request flow with coverage check."""

    def test_blocked_when_existing_skill_covers(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用")
        before_count = store.pending_count()
        coverage_result = {
            "decision": "existing_covered",
            "confidence": 0.92,
            "skill_name": "k8s-deploy",
            "reason_zh": "已有技能已覆盖",
        }
        req = store.create_request(
            action="create", skill_name="k8s-deploy-v2", reason="部署 K8s",
            proposed_content="---\nname: k8s-deploy-v2\ndescription: 部署 K8s\n---\nBody",
            coverage_result=coverage_result,
        )
        assert req.status == "covered_by_existing"
        assert req.related_existing_skill_ids is not None
        # Verify no row was inserted into DB
        assert store.pending_count() == before_count

    def test_related_existing_still_creates_pending(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用")
        coverage_result = {
            "decision": "existing_related_but_distinct",
            "confidence": 0.78,
            "skill_name": "k8s-deploy",
            "reason_zh": "相关但侧重不同场景",
        }
        req = store.create_request(
            action="create", skill_name="k8s-monitor", reason="K8s 监控",
            proposed_content="---\nname: k8s-monitor\ndescription: K8s 监控\n---\nBody",
            coverage_result=coverage_result,
        )
        assert req.status == "pending"
        assert req.existing_coverage_status == "related_existing"
        assert req.related_existing_skill_ids is not None

    def test_no_match_creates_normal_pending(self, store: SkillChangeStore, skills_dir: Path):
        _write_skill(skills_dir, "python-test", "Python 测试")
        coverage_result = {
            "decision": "no_existing_match",
            "confidence": 0.90,
            "skill_name": None,
            "reason_zh": "无匹配",
        }
        req = store.create_request(
            action="create", skill_name="terraform-aws", reason="Terraform",
            proposed_content="---\nname: terraform-aws\ndescription: Terraform AWS\n---\nBody",
            coverage_result=coverage_result,
        )
        assert req.status == "pending"
        assert req.existing_coverage_status is None

    def test_blacklist_has_priority_over_coverage(self, store: SkillChangeStore, skills_dir: Path):
        """Blacklist hit should take priority over existing coverage."""
        _write_skill(skills_dir, "spam-email", "垃圾邮件")
        judge_result = {
            "decision": "blacklist_hit",
            "confidence": 0.95,
            "target_id": None,
            "reason_zh": "命中黑名单",
        }
        coverage_result = {
            "decision": "no_existing_match",
            "confidence": 0.90,
            "skill_name": None,
            "reason_zh": "无匹配",
        }
        req = store.create_request(
            action="create", skill_name="spam-email", reason="垃圾邮件",
            proposed_content="---\nname: spam-email\ndescription: 垃圾\n---\nBody",
            judge_result=judge_result,
            coverage_result=coverage_result,
        )
        assert req.status == "blocked_by_blacklist"

    def test_existing_coverage_runs_before_pending_duplicate(self, store: SkillChangeStore, skills_dir: Path):
        """If existing skill covers, should not even check pending duplicates."""
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用")
        # Create a pending for same skill
        store.create_request(
            action="create", skill_name="k8s-deploy", reason="第一次",
            proposed_content="---\nname: k8s-deploy\ndescription: 部署\n---\nBody1",
        )
        # Now try to create with coverage covered
        coverage_result = {
            "decision": "existing_covered",
            "confidence": 0.92,
            "skill_name": "k8s-deploy",
            "reason_zh": "已有技能覆盖",
        }
        req = store.create_request(
            action="create", skill_name="k8s-deploy-v2", reason="第二次",
            proposed_content="---\nname: k8s-deploy-v2\ndescription: 部署v2\n---\nBody2",
            coverage_result=coverage_result,
        )
        assert req.status == "covered_by_existing"

    def test_edit_action_not_blocked_by_coverage(self, store: SkillChangeStore, skills_dir: Path):
        """Coverage check should NOT block edit/patch/delete — only create."""
        _write_skill(skills_dir, "k8s-deploy", "部署 Kubernetes 应用")
        coverage_result = {
            "decision": "existing_covered",
            "confidence": 0.92,
            "skill_name": "k8s-deploy",
            "reason_zh": "已有技能已覆盖",
        }
        # Edit action should be allowed even if coverage says "covered"
        req = store.create_request(
            action="edit", skill_name="k8s-deploy", reason="更新部署流程",
            proposed_content="---\nname: k8s-deploy\ndescription: 更新部署\n---\nBody2",
            coverage_result=coverage_result,
        )
        assert req.status == "pending"
        assert store.pending_count() == 1


# ── Test: to_dict includes new fields ────────────────────────────────────────


class TestToDictIncludesRelatedExisting:
    """Test that to_dict returns the new fields."""

    def test_pending_with_related_existing(self, store: SkillChangeStore, skills_dir: Path):
        coverage_result = {
            "decision": "existing_related_but_distinct",
            "confidence": 0.78,
            "skill_name": "existing-skill",
            "reason_zh": "相关但不覆盖",
        }
        req = store.create_request(
            action="create", skill_name="new-skill", reason="测试",
            proposed_content="---\nname: new-skill\ndescription: 新技能\n---\nBody",
            coverage_result=coverage_result,
        )
        d = req.to_dict()
        assert "related_existing_skill_ids" in d
        assert "related_existing_skill_note" in d
        assert "existing_coverage_status" in d
        assert d["existing_coverage_status"] == "related_existing"

    def test_covered_by_existing_to_dict(self, store: SkillChangeStore, skills_dir: Path):
        coverage_result = {
            "decision": "existing_covered",
            "confidence": 0.92,
            "skill_name": "existing-skill",
            "reason_zh": "已覆盖",
        }
        req = store.create_request(
            action="create", skill_name="new-skill", reason="测试",
            proposed_content="---\nname: new-skill\ndescription: 新\n---\nBody",
            coverage_result=coverage_result,
        )
        d = req.to_dict()
        assert d["status"] == "covered_by_existing"
        assert d["existing_coverage_status"] == "covered_by_existing"
        ids = json.loads(d["related_existing_skill_ids"] or "[]")
        assert "existing-skill" in ids

    def test_normal_pending_has_none_fields(self, store: SkillChangeStore):
        req = store.create_request(
            action="create", skill_name="new-skill", reason="测试",
            proposed_content="---\nname: new-skill\ndescription: 新\n---\nBody",
        )
        d = req.to_dict()
        assert d["related_existing_skill_ids"] is None
        assert d["related_existing_skill_note"] is None
        assert d["existing_coverage_status"] is None
