"""Unit tests for ``merge_task_progress_sync_to_disk`` (single-seam disk persist).

These tests pin down the merge behavior the bridge layer relies on:

1. **Match by ``moduleId``** — unknown modules are skipped, never appended.
2. **Index-based ``completed`` update** — only when task counts match exactly;
   the on-disk task ``name`` is preserved (drivers may emit English slugs
   while the persisted file holds the Chinese ``displayName``).
3. **No-op writes are skipped** — incoming flags equal to disk yields no I/O.
4. **Disk corruption / missing payload are non-fatal** — a structured report is
   returned with ``skipped`` reasons; nothing raises.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nanobot.web import task_progress as tp


@pytest.fixture
def isolated_progress_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``task_progress_file_path()`` to a temp file via env override."""
    target = tmp_path / "task_progress.json"
    monkeypatch.setenv("NANOBOT_TASK_PROGRESS_FILE", str(target))
    return target


def _seed_disk(path: Path, *, jm_completed: list[bool] | None = None) -> None:
    payload = tp.default_task_progress_file_payload()
    if jm_completed is not None:
        jm = next(p for p in payload["progress"] if p["moduleId"] == "job_management")
        for i, t in enumerate(jm["tasks"]):
            if i < len(jm_completed):
                t["completed"] = bool(jm_completed[i])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_merge_updates_matching_module_by_index(isolated_progress_file: Path) -> None:
    """Driver pushes 6 English-slug tasks for ``job_management``; disk has 6 Chinese
    names. Index-based merge flips ``completed`` flags without touching the names."""
    _seed_disk(isolated_progress_file)

    incoming = {
        "schemaVersion": 1,
        "modules": [
            {
                "moduleId": "job_management",
                "moduleName": "Jobs",
                "tasks": [
                    {"name": "upload_inputs", "completed": True},
                    {"name": "files_uploaded", "completed": True},
                    {"name": "plan_design", "completed": True},
                    {"name": "plan_install", "completed": False},
                    {"name": "plan_join", "completed": False},
                    {"name": "closed", "completed": False},
                ],
            }
        ],
    }

    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is True
    assert report["merged_module_ids"] == ["job_management"]
    assert report["skipped"] == []

    persisted = json.loads(isolated_progress_file.read_text(encoding="utf-8"))
    jm = next(p for p in persisted["progress"] if p["moduleId"] == "job_management")
    flags = [t["completed"] for t in jm["tasks"]]
    assert flags == [True, True, True, False, False, False]
    # File-side Chinese names must NOT be overwritten with English slugs.
    names = [t["name"] for t in jm["tasks"]]
    assert names == [
        "作业待启动",
        "资料已上传",
        "规划设计排期已确认",
        "工程安装排期已确认",
        "集群联调排期已确认",
        "作业闭环完成",
    ]
    assert jm["updatedAt"] is not None
    assert persisted["updatedAt"] is not None


def test_merge_skips_unknown_module_id(isolated_progress_file: Path) -> None:
    """The merger must NOT append unknown modules to the on-disk ``progress[]`` list
    — appending would pollute the top stepper / overall counts. Use a definitely
    unknown ID so this stays a pure regression test for the *skip* branch even as
    the platform's default schema evolves."""
    _seed_disk(isolated_progress_file)
    snapshot_before = isolated_progress_file.read_text(encoding="utf-8")

    incoming = {
        "schemaVersion": 1,
        "modules": [
            {
                # Definitely not in default seed and never will be.
                "moduleId": "future_phase_unknown_xyz",
                "tasks": [{"name": "x", "completed": True}] * 5,
            }
        ],
    }

    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is False
    assert report["merged_module_ids"] == []
    assert report["skipped"] == [
        {"moduleId": "future_phase_unknown_xyz", "reason": "not_in_disk"}
    ]
    # File untouched (byte-identical).
    assert isolated_progress_file.read_text(encoding="utf-8") == snapshot_before


def test_merge_writes_jmfz_under_canonical_module_id(
    isolated_progress_file: Path,
) -> None:
    """Regression: ``jmfz`` driver was emitting ``moduleId="jmfz"`` while the on-disk
    canonical id is ``modeling_simulation_workbench``. After the alignment fix
    (driver + default schema both use the canonical id), a 5-task driver payload
    must land on disk without skipping. Pinning the canonical id here also guards
    against future drift in either direction."""
    _seed_disk(isolated_progress_file)

    incoming = {
        "schemaVersion": 1,
        "modules": [
            {
                "moduleId": "modeling_simulation_workbench",
                "moduleName": "建模仿真",
                "tasks": [
                    {"name": "boq", "completed": True},
                    {"name": "device", "completed": True},
                    {"name": "create", "completed": False},
                    {"name": "topo_c", "completed": False},
                    {"name": "link", "completed": False},
                ],
            }
        ],
    }

    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is True
    assert report["merged_module_ids"] == ["modeling_simulation_workbench"]
    assert report["skipped"] == []
    persisted = json.loads(isolated_progress_file.read_text(encoding="utf-8"))
    sim = next(
        p for p in persisted["progress"] if p["moduleId"] == "modeling_simulation_workbench"
    )
    assert [t["completed"] for t in sim["tasks"]] == [True, True, False, False, False]
    # Chinese names on disk preserved (driver emits English slugs).
    assert [t["name"] for t in sim["tasks"]] == [
        "BOQ 提取",
        "设备确认",
        "创建设备",
        "拓扑确认",
        "拓扑连接",
    ]


def test_merge_skips_on_task_count_mismatch(isolated_progress_file: Path) -> None:
    """Driver pushes 5 tasks for a module that has 6 on disk → skip + warn."""
    _seed_disk(isolated_progress_file)
    snapshot_before = isolated_progress_file.read_text(encoding="utf-8")

    incoming = {
        "schemaVersion": 1,
        "modules": [
            {
                "moduleId": "job_management",
                "tasks": [{"name": f"t{i}", "completed": True} for i in range(5)],
            }
        ],
    }

    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is False
    assert report["merged_module_ids"] == []
    assert report["skipped"] == [
        {
            "moduleId": "job_management",
            "reason": "task_count_mismatch:disk=6,incoming=5",
        }
    ]
    assert isolated_progress_file.read_text(encoding="utf-8") == snapshot_before


def test_merge_no_change_does_not_rewrite(isolated_progress_file: Path) -> None:
    """Incoming flags equal to disk → no rewrite; ``wrote_disk=False``,
    ``merged_module_ids`` empty (nothing actually changed)."""
    _seed_disk(isolated_progress_file, jm_completed=[True, False, False, False, False, False])
    mtime_before = os.path.getmtime(isolated_progress_file)

    incoming = {
        "modules": [
            {
                "moduleId": "job_management",
                "tasks": [
                    {"completed": True},
                    {"completed": False},
                    {"completed": False},
                    {"completed": False},
                    {"completed": False},
                    {"completed": False},
                ],
            }
        ]
    }

    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is False
    assert report["merged_module_ids"] == []
    assert report["skipped"] == []
    assert os.path.getmtime(isolated_progress_file) == mtime_before


def test_merge_creates_default_file_when_missing(
    isolated_progress_file: Path,
) -> None:
    """File doesn't exist → seed from default + merge in one shot.

    This is the boot-from-scratch path; without it, the very first
    ``task_progress.sync`` after install would silently no-op.
    """
    assert not isolated_progress_file.exists()

    incoming = {
        "modules": [
            {
                "moduleId": "smart_survey",
                "tasks": [
                    {"completed": True},
                    {"completed": True},
                    {"completed": False},
                    {"completed": False},
                ],
            }
        ]
    }

    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is True
    assert report["merged_module_ids"] == ["smart_survey"]
    persisted = json.loads(isolated_progress_file.read_text(encoding="utf-8"))
    survey = next(p for p in persisted["progress"] if p["moduleId"] == "smart_survey")
    assert [t["completed"] for t in survey["tasks"]] == [True, True, False, False]


def test_merge_handles_corrupt_disk_file(isolated_progress_file: Path) -> None:
    """Corrupt JSON on disk must not raise — return structured report instead."""
    isolated_progress_file.write_text("not-json {{", encoding="utf-8")

    incoming = {"modules": [{"moduleId": "job_management", "tasks": []}]}
    report = tp.merge_task_progress_sync_to_disk(incoming)

    assert report["wrote_disk"] is False
    assert any(s["moduleId"] == "*" and "disk_unreadable" in s["reason"] for s in report["skipped"])


def test_merge_ignores_non_dict_payload() -> None:
    """Defensive: random shapes must not raise."""
    assert tp.merge_task_progress_sync_to_disk(None) == {  # type: ignore[arg-type]
        "merged_module_ids": [],
        "skipped": [],
        "wrote_disk": False,
    }
    assert tp.merge_task_progress_sync_to_disk({"modules": "not-a-list"}) == {
        "merged_module_ids": [],
        "skipped": [],
        "wrote_disk": False,
    }


def test_normalize_dedupes_progress_modules_by_id() -> None:
    """``progress[]`` 里同 ``moduleId`` 出现多次时只保留首条；防止前端 stepper 的
    ``key={m.taskModuleId || m.moduleId}`` 因 id 重复而崩 React。

    场景：旧版 jmfz driver 用 ``moduleId=jmfz``、后改名为 ``modeling_simulation_workbench``
    且 ``default_task_progress_file_payload`` 也写过同名条目时会留下重复历史行。
    """
    raw = {
        "schemaVersion": 1,
        "updatedAt": None,
        "progress": [
            {
                "moduleId": "smart_survey",
                "moduleName": "智慧工勘",
                "tasks": [
                    {"name": "场景筛选与底表过滤", "completed": True},
                    {"name": "勘测数据汇总", "completed": True},
                    {"name": "报告生成", "completed": True},
                    {"name": "审批与分发闭环", "completed": True},
                ],
            },
            {
                "moduleId": "smart_survey",
                "moduleName": "智慧工勘模块",
                "tasks": [
                    {"name": "场景筛选与底表过滤", "completed": True},
                    {"name": "勘测数据汇总", "completed": True},
                    {"name": "报告生成", "completed": True},
                    {"name": "审批分发", "completed": True},
                ],
            },
            {
                "moduleId": "modeling_simulation_workbench",
                "moduleName": "建模仿真",
                "tasks": [
                    {"name": "BOQ 提取", "completed": False},
                ],
            },
        ],
    }

    normalized = tp.normalize_task_progress_payload(raw)

    module_ids = [m["id"] for m in normalized["modules"]]
    assert module_ids == ["smart_survey", "modeling_simulation_workbench"]
    survey = next(m for m in normalized["modules"] if m["id"] == "smart_survey")
    # First-occurrence wins → keep the canonical Chinese name and task list.
    assert survey["name"] == "智慧工勘"
    assert [s["name"] for s in survey["steps"]] == [
        "场景筛选与底表过滤",
        "勘测数据汇总",
        "报告生成",
        "审批与分发闭环",
    ]


def test_normalize_dedupes_modules_in_overall_branch() -> None:
    """``modules + overall`` payload 直接由 driver 发出时，若同 ``id`` 出现多次也去重。"""
    raw = {
        "modules": [
            {"id": "smart_survey", "name": "A", "status": "completed", "steps": []},
            {"id": "smart_survey", "name": "B", "status": "running", "steps": []},
            {"id": "modeling_simulation_workbench", "name": "C", "status": "pending", "steps": []},
        ],
        "overall": {"doneCount": 1, "totalCount": 2},
    }

    normalized = tp.normalize_task_progress_payload(raw)

    ids = [m["id"] for m in normalized["modules"]]
    assert ids == ["smart_survey", "modeling_simulation_workbench"]
    survey = next(m for m in normalized["modules"] if m["id"] == "smart_survey")
    assert survey["name"] == "A"  # first wins
