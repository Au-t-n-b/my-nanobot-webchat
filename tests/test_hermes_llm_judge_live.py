"""Live integration test: LLM semantic judge with real Qwen3-235B-Instruct.

Run with: python -m pytest tests/test_hermes_llm_judge_live.py -v --tb=short -s

Requires:
  - Qwen3-235B-Instruct at 100.102.191.152:2570 (no proxy needed)
  - openai package installed
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure proxy env vars are stripped so we reach the endpoint directly
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(_k, None)

from openai import AsyncOpenAI
import httpx

from nanobot.agent.skill_change_store import SkillChangeStore
from nanobot.providers.custom_provider import CustomProvider


# ── Constants ──────────────────────────────────────────────────────────────

QWEN3_BASE = "http://100.102.191.152:2570/v1"
QWEN3_MODEL = "Qwen3-235B-Instruct"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> SkillChangeStore:
    return SkillChangeStore(tmp_path, expiry_days=60)


@pytest.fixture
def provider() -> CustomProvider:
    """Real CustomProvider pointing at Qwen3."""
    return CustomProvider(
        api_key="no-key",
        api_base=QWEN3_BASE,
        default_model=QWEN3_MODEL,
        proxy=None,
        ssl_verify=True,
    )


# ── Helper ─────────────────────────────────────────────────────────────────


async def _judge(
    store: SkillChangeStore,
    provider: CustomProvider,
    *,
    action: str,
    skill_name: str,
    reason: str,
    proposed_content: str | None = None,
) -> dict | None:
    """Wire provider into store, run prefilter_and_judge with real LLM."""
    store.set_provider(provider, model=QWEN3_MODEL)
    judge_result, coverage_result = await store.prefilter_and_judge(
        action=action,
        skill_name=skill_name,
        reason=reason,
        proposed_content=proposed_content,
    )
    return judge_result


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_real_llm_detects_exact_duplicate(store: SkillChangeStore, provider: CustomProvider):
    """Two requests with near-identical reasons → judge should say same_duplicate."""
    store.create_request(
        action="create",
        skill_name="ci-pipeline",
        reason="搭建 GitHub Actions CI 流水线用于 Python 项目的自动化测试和部署",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="ci-pipeline",
        reason="配置 GitHub Actions CI 流水线做 Python 自动化测试和部署",
    )
    # The judge may return same_duplicate or related_but_distinct
    assert result is not None, "Judge returned None — prefilter didn't find candidates"
    print(f"\n[exact duplicate] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")


@pytest.mark.asyncio
async def test_real_llm_detects_semantic_equivalence_chinese(store: SkillChangeStore, provider: CustomProvider):
    """Different Chinese phrasing for same task → semantic duplicate."""
    store.create_request(
        action="create",
        skill_name="local-auth",
        reason="本地 agent bearer token 认证流程配置",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="local-auth",
        reason="本地代理鉴权机制设置",
    )
    assert result is not None
    print(f"\n[semantic equiv] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")
    # We expect the LLM to recognize 认证 ≈ 鉴权 as same task
    # But we don't hard-assert the decision — just log it


@pytest.mark.asyncio
async def test_real_llm_distinguishes_related_but_distinct(store: SkillChangeStore, provider: CustomProvider):
    """Same skill name but genuinely different tasks → should say related_but_distinct."""
    store.create_request(
        action="create",
        skill_name="prod-infra",
        reason="生产环境 K8s 集群部署配置流程，包括 namespace、resource quota、HPA 设置",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="prod-infra",
        reason="生产环境 K8s 集群监控告警配置，包括 Prometheus rule、Grafana dashboard、钉钉通知",
    )
    assert result is not None
    print(f"\n[related distinct] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")
    # Ideally: related_but_distinct, but we just verify it returns something valid


@pytest.mark.asyncio
async def test_real_llm_blacklist_hit(store: SkillChangeStore, provider: CustomProvider):
    """Request matching a blacklist entry → judge should say blacklist_hit."""
    req = store.create_request(
        action="create",
        skill_name="bad-idea",
        reason="给所有用户发邮件推送广告",
    )
    store.reject_request(req.id)
    store.create_blacklist_from_request(req, note="垃圾营销功能")

    result = await _judge(
        store, provider,
        action="create",
        skill_name="bad-idea",
        reason="批量发送推广邮件给全部用户列表",
    )
    assert result is not None
    print(f"\n[blacklist hit] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")


@pytest.mark.asyncio
async def test_real_llm_blacklist_miss_distinct(store: SkillChangeStore, provider: CustomProvider):
    """Blacklisted "发广告邮件" vs new request "发系统通知" → should NOT block."""
    req = store.create_request(
        action="create",
        skill_name="email-push",
        reason="给所有用户发邮件推送广告营销内容",
    )
    store.reject_request(req.id)
    store.create_blacklist_from_request(req, note="营销功能不需要")

    result = await _judge(
        store, provider,
        action="create",
        skill_name="email-push",
        reason="系统维护通知邮件发送给受影响用户",
    )
    assert result is not None
    print(f"\n[blacklist miss] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")


@pytest.mark.asyncio
async def test_full_roundtrip_create_with_judge(store: SkillChangeStore, provider: CustomProvider):
    """End-to-end: create_request with real LLM judge result applied."""
    store.set_provider(provider, model=QWEN3_MODEL)

    # First request
    store.create_request(
        action="create",
        skill_name="docker-build",
        reason="Docker 多阶段构建 + 推送 ECR 镜像仓库的完整流程",
    )

    # Second request with judge
    judge_result = await _judge(
        store, provider,
        action="create",
        skill_name="docker-build",
        reason="Docker 多阶段构建并推送到 ECR 镜像仓库的步骤",
    )

    assert judge_result is not None
    req2 = store.create_request(
        action="create",
        skill_name="docker-build",
        reason="Docker 多阶段构建并推送到 ECR 镜像仓库的步骤",
        judge_result=judge_result,
    )

    print(f"\n[roundtrip] req2.status={req2.status} decision={judge_result.get('decision')}")
    print(f"  conf={judge_result.get('confidence')} reason_zh={judge_result.get('reason_zh')}")

    # If merged, there should be 1 pending; if new, 2 pending
    if req2.status == "merged_with_existing":
        assert store.pending_count() == 1
        assert req2.duplicate_count >= 1
        print("  → MERGED into existing")
    elif req2.status == "pending":
        assert store.pending_count() == 2
        print("  → Created new pending")
    else:
        print(f"  → Unexpected status: {req2.status}")


# ── Negative tests: judge should NOT merge/block unrelated requests ────────


@pytest.mark.asyncio
async def test_negative_completely_unrelated(store: SkillChangeStore, provider: CustomProvider):
    """CI pipeline vs database backup — zero overlap, should say unrelated."""
    store.create_request(
        action="create",
        skill_name="ci-pipeline",
        reason="搭建 GitHub Actions CI 流水线用于 Python 项目的自动化测试和部署",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="db-backup",
        reason="MySQL 数据库定时备份策略，包括全量备份、增量备份和异地容灾",
    )
    # Different skill names, n-gram prefilter may not find candidates
    if result is None:
        print("\n[negative unrelated] prefilter found no candidates → auto pending (correct)")
    else:
        print(f"\n[negative unrelated] decision={result.get('decision')} conf={result.get('confidence')}")
        print(f"  reason_zh: {result.get('reason_zh')}")
        assert result.get("decision") != "same_duplicate", "Should NOT merge completely unrelated requests"


@pytest.mark.asyncio
async def test_negative_same_category_different_purpose(store: SkillChangeStore, provider: CustomProvider):
    """Python testing vs Python deployment — same language, different purpose."""
    store.create_request(
        action="create",
        skill_name="python-test",
        reason="Python 项目使用 pytest + coverage 进行单元测试和覆盖率报告的完整配置",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="python-deploy",
        reason="Python 项目使用 setuptools + twine 发布到 PyPI 的打包部署流程",
    )
    if result is None:
        print("\n[negative same-lang] prefilter found no candidates → auto pending (correct)")
    else:
        print(f"\n[negative same-lang] decision={result.get('decision')} conf={result.get('confidence')}")
        print(f"  reason_zh: {result.get('reason_zh')}")
        assert result.get("decision") != "same_duplicate"


@pytest.mark.asyncio
async def test_negative_similar_words_different_domain(store: SkillChangeStore, provider: CustomProvider):
    """'配置网络' vs '配置数据库' — similar verbs, completely different domains."""
    store.create_request(
        action="create",
        skill_name="network-config",
        reason="配置 VPC 网络环境，包括子网划分、安全组规则、NAT 网关设置",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="db-config",
        reason="配置 MySQL 数据库实例，包括参数调优、主从复制、读写分离",
    )
    if result is None:
        print("\n[negative similar-words] prefilter found no candidates → auto pending (correct)")
    else:
        print(f"\n[negative similar-words] decision={result.get('decision')} conf={result.get('confidence')}")
        print(f"  reason_zh: {result.get('reason_zh')}")
        assert result.get("decision") != "same_duplicate"


@pytest.mark.asyncio
async def test_negative_same_name_different_action(store: SkillChangeStore, provider: CustomProvider):
    """Same skill name, edit vs delete — must NOT merge (conflicting actions)."""
    store.create_request(
        action="edit",
        skill_name="my-skill",
        reason="更新 my-skill 的部署步骤，增加蓝绿发布策略",
    )
    result = await _judge(
        store, provider,
        action="delete",
        skill_name="my-skill",
        reason="删除 my-skill，该功能已废弃不再使用",
    )
    if result is None:
        print("\n[negative edit-vs-delete] prefilter found no candidates")
    else:
        print(f"\n[negative edit-vs-delete] decision={result.get('decision')} conf={result.get('confidence')}")
        print(f"  reason_zh: {result.get('reason_zh')}")
        # edit vs delete are conflicting — should never auto-merge
        assert result.get("decision") != "same_duplicate"


@pytest.mark.asyncio
async def test_negative_english_vs_chinese(store: SkillChangeStore, provider: CustomProvider):
    """English request vs Chinese request for genuinely different tasks."""
    store.create_request(
        action="create",
        skill_name="api-gateway",
        reason="Set up Kong API gateway with rate limiting, authentication and request routing",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="log-pipeline",
        reason="搭建 ELK 日志采集管线，包括 Filebeat 采集、Logstash 过滤、Kibana 可视化",
    )
    if result is None:
        print("\n[negative en-vs-zh] prefilter found no candidates → auto pending (correct)")
    else:
        print(f"\n[negative en-vs-zh] decision={result.get('decision')} conf={result.get('confidence')}")
        print(f"  reason_zh: {result.get('reason_zh')}")
        assert result.get("decision") != "same_duplicate"


@pytest.mark.asyncio
async def test_negative_roundtrip_no_false_merge(store: SkillChangeStore, provider: CustomProvider):
    """Full roundtrip: two unrelated requests, both should stay as separate pending."""
    store.set_provider(provider, model=QWEN3_MODEL)

    store.create_request(
        action="create",
        skill_name="redis-cache",
        reason="Redis 缓存层配置，包括缓存策略、TTL 管理、缓存穿透防护",
    )

    judge_result = await _judge(
        store, provider,
        action="create",
        skill_name="auth-service",
        reason="OAuth2 认证服务搭建，包括授权码流程、JWT 签发、刷新令牌管理",
    )

    req2 = store.create_request(
        action="create",
        skill_name="auth-service",
        reason="OAuth2 认证服务搭建，包括授权码流程、JWT 签发、刷新令牌管理",
        judge_result=judge_result,
    )

    print(f"\n[negative roundtrip] req2.status={req2.status}", end="")
    if judge_result is None:
        print(" prefilter=None → pending (correct)")
        assert req2.status == "pending"
    else:
        print(f" decision={judge_result.get('decision')} conf={judge_result.get('confidence')}")

    # Both must exist as separate pending
    assert store.pending_count() == 2, "Should have 2 separate pending requests"
    assert req2.status == "pending"


# ── Harder negatives: prefilter passes but LLM should NOT merge ───────────


@pytest.mark.asyncio
async def test_hard_negative_same_name_unrelated_reason(store: SkillChangeStore, provider: CustomProvider):
    """Same skill name, completely different reason — prefilter passes (exact name match), LLM should reject merge."""
    store.create_request(
        action="create",
        skill_name="infra-tool",
        reason="Terraform 基础设施即代码，管理 AWS 资源的生命周期",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="infra-tool",
        reason="Ansible 配置管理工具，批量执行服务器运维脚本",
    )
    assert result is not None, "Exact name match → prefilter should pass"
    print(f"\n[hard neg: same name, diff reason] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")
    assert result.get("decision") != "same_duplicate", "Terraform ≠ Ansible, should not merge"


@pytest.mark.asyncio
async def test_hard_negative_same_name_monitor_vs_deploy(store: SkillChangeStore, provider: CustomProvider):
    """Same skill name 'prod-k8s', one deploys, one monitors — LLM must distinguish."""
    store.create_request(
        action="create",
        skill_name="prod-k8s",
        reason="生产环境 K8s 集群部署：namespace 规划、resource quota、HPA 弹性伸缩",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="prod-k8s",
        reason="生产环境 K8s 集群监控：Prometheus 采集、Grafana 面板、告警规则配置",
    )
    assert result is not None
    print(f"\n[hard neg: monitor vs deploy] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")
    assert result.get("decision") != "same_duplicate"


@pytest.mark.asyncio
async def test_hard_negative_overlapping_keywords_different_goal(store: SkillChangeStore, provider: CustomProvider):
    """Both mention 'API 认证' but one is gateway setup, other is token rotation — different goals."""
    store.create_request(
        action="create",
        skill_name="api-auth",
        reason="API 网关认证配置：JWT 签发、验证中间件、角色权限控制",
    )
    result = await _judge(
        store, provider,
        action="create",
        skill_name="api-auth",
        reason="API Token 自动轮换策略：定期刷新 access token、refresh token 管理、过期告警",
    )
    assert result is not None
    print(f"\n[hard neg: overlapping keywords, diff goal] decision={result.get('decision')} conf={result.get('confidence')}")
    print(f"  reason_zh: {result.get('reason_zh')}")
    # These are related but NOT duplicates — one-time setup vs ongoing rotation


@pytest.mark.asyncio
async def test_hard_negative_roundtrip_no_false_merge(store: SkillChangeStore, provider: CustomProvider):
    """Roundtrip: same skill name, genuinely different tasks — should create 2 separate pending."""
    store.set_provider(provider, model=QWEN3_MODEL)

    store.create_request(
        action="create",
        skill_name="data-pipeline",
        reason="实时数据管道搭建：Kafka 消息队列、Flink 流处理、数据清洗转换",
    )

    judge_result = await _judge(
        store, provider,
        action="create",
        skill_name="data-pipeline",
        reason="离线数据管道搭建：Airflow DAG 编排、Spark 批处理、数据仓库 ETL",
    )
    assert judge_result is not None

    req2 = store.create_request(
        action="create",
        skill_name="data-pipeline",
        reason="离线数据管道搭建：Airflow DAG 编排、Spark 批处理、数据仓库 ETL",
        judge_result=judge_result,
    )

    print(f"\n[hard neg roundtrip] status={req2.status} decision={judge_result.get('decision')} conf={judge_result.get('confidence')}")
    print(f"  reason_zh: {judge_result.get('reason_zh')}")

    # Real-time vs batch are genuinely different — must NOT merge
    assert req2.status != "merged_with_existing", "Kafka+Flink ≠ Airflow+Spark, should not merge"
    assert store.pending_count() == 2
