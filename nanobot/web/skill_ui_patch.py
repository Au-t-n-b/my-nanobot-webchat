"""SDUI v3 — SkillUiDataPatch helpers for SSE (/api/chat).

Build payloads with :func:`build_skill_ui_data_patch_payload`, then emit them via
:func:`nanobot.agent.loop.emit_skill_ui_data_patch_event` when running inside a
chat request that bound an emitter (see ``routes.handle_chat``).

Higher-level: :class:`SkillUiPatchPusher` (or :func:`push_gc_dashboard_node_merge`) builds
``merge`` ops and pushes in one call — no hand-written ``ops`` JSON.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from loguru import logger
from urllib.parse import parse_qs

# ── Process-wide revision counter (per docId) ─────────────────────────────
_SKILL_UI_PATCH_REVISION_LOCK = asyncio.Lock()
_SKILL_UI_PATCH_REVISION_BY_DOC: dict[str, int] = {}

SDUI_GC_DASHBOARD_DOC_ID = "dashboard:gc"

# Default skill-ui URL for GC dashboard JSON (override with NANOBOT_GC_DASHBOARD_SYNTHETIC_PATH).
DEFAULT_GC_SYNTHETIC_PATH = "skill-ui://SduiView?dataFile=workspace/dashboard.json"


def default_gc_synthetic_path() -> str:
    """Resolved default path for GC dashboard patches (env or built-in default)."""
    return (os.environ.get("NANOBOT_GC_DASHBOARD_SYNTHETIC_PATH") or "").strip() or DEFAULT_GC_SYNTHETIC_PATH


def validate_skill_ui_synthetic_path(path: str) -> tuple[bool, str]:
    """Return (ok, reason_code). Used before emitting SkillUiDataPatch."""
    p = (path or "").strip()
    if not p:
        return False, "empty"
    if not p.startswith("skill-ui://"):
        return False, "bad_scheme"
    rest = p[len("skill-ui://") :]
    if not rest.startswith("SduiView?"):
        return False, "not_sduiview"
    q = rest[len("SduiView?") :]
    qs = parse_qs(q, keep_blank_values=True)
    df = (qs.get("dataFile") or [""])[0]
    if not str(df).strip():
        return False, "missing_datafile"
    return True, ""


async def next_skill_ui_data_patch_revision(doc_id: str) -> int:
    """Per-docId monotonic revision for SkillUiDataPatch (process-wide)."""
    async with _SKILL_UI_PATCH_REVISION_LOCK:
        n = _SKILL_UI_PATCH_REVISION_BY_DOC.get(doc_id, 0) + 1
        _SKILL_UI_PATCH_REVISION_BY_DOC[doc_id] = n
        return n


async def build_skill_ui_data_patch_payload(
    *,
    synthetic_path: str,
    ops: list[dict[str, Any]],
    doc_id: str = SDUI_GC_DASHBOARD_DOC_ID,
) -> dict[str, Any]:
    """Validate path, assign revision, return SSE ``data`` object for SkillUiDataPatch."""
    ok, reason = validate_skill_ui_synthetic_path(synthetic_path)
    if not ok:
        logger.warning(
            "skill_ui_patch_build_failed | reason=invalid_synthetic_path | code={} | path={!r}",
            reason,
            (synthetic_path or "")[:500],
        )
        raise ValueError(f"invalid syntheticPath: {reason}")
    revision = await next_skill_ui_data_patch_revision(doc_id)
    return {
        "syntheticPath": synthetic_path.strip(),
        "patch": {
            "schemaVersion": 3,
            "type": "SduiPatch",
            "docId": doc_id,
            "revision": revision,
            "ops": ops,
        },
    }


def build_append_op(*, node_id: str, field: str, value: Any) -> dict[str, Any]:
    """Build a v3 ``append`` op (e.g. ArtifactGrid.artifacts)."""
    nid = (node_id or "").strip()
    if not nid:
        raise ValueError("append op requires non-empty node_id")
    f = (field or "").strip()
    if not f:
        raise ValueError("append op requires non-empty field")
    return {
        "op": "append",
        "target": {"by": "id", "nodeId": nid, "field": f},
        "value": value,
    }


def _merge_op_for_node(node_id: str, node_type: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Single ``merge`` op: ``value`` includes ``type`` + ``id`` + *fields* (M1 leaf updates)."""
    merged = dict(fields)
    merged["type"] = node_type
    merged["id"] = node_id
    return {
        "op": "merge",
        "target": {"by": "id", "nodeId": node_id},
        "value": merged,
    }


class SkillUiPatchPusher:
    """Builds merge Patch payloads for a fixed ``syntheticPath`` / ``docId`` and emits via SSE.

    Example::

        pusher = SkillUiPatchPusher()
        await pusher.update_node("stat-1", "Statistic", {"value": "45%", "color": "warning"})
    """

    def __init__(
        self,
        synthetic_path: str | None = None,
        *,
        doc_id: str = SDUI_GC_DASHBOARD_DOC_ID,
    ) -> None:
        self._synthetic_path = (synthetic_path or "").strip() or default_gc_synthetic_path()
        self._doc_id = doc_id

    @property
    def synthetic_path(self) -> str:
        return self._synthetic_path

    @property
    def doc_id(self) -> str:
        return self._doc_id

    async def update_node(self, node_id: str, node_type: str, fields: dict[str, Any]) -> None:
        """One ``merge`` op for ``target.by=id``; ``fields`` are merged into the node (leaf fields)."""
        await self.update_nodes([(node_id.strip(), node_type, dict(fields))])

    async def update_nodes(self, updates: list[tuple[str, str, dict[str, Any]]]) -> None:
        """Multiple merge ops in a single Patch (one revision)."""
        if not updates:
            return
        ops: list[dict[str, Any]] = []
        for node_id, node_type, fields in updates:
            nid = node_id.strip()
            if not nid or not node_type.strip():
                continue
            ops.append(_merge_op_for_node(nid, node_type.strip(), fields))
        if not ops:
            return
        payload = await build_skill_ui_data_patch_payload(
            synthetic_path=self._synthetic_path,
            doc_id=self._doc_id,
            ops=ops,
        )
        # Lazy import avoids import cycle (agent.loop ↔ tools ↔ skill_ui_patch).
        from nanobot.agent.loop import emit_skill_ui_data_patch_event

        await emit_skill_ui_data_patch_event(payload)


async def push_gc_dashboard_node_merge(
    node_id: str,
    node_type: str,
    fields: dict[str, Any],
    *,
    synthetic_path: str | None = None,
    doc_id: str = SDUI_GC_DASHBOARD_DOC_ID,
) -> None:
    """One-liner: merge-update a single node on the GC dashboard and emit."""
    pusher = SkillUiPatchPusher(synthetic_path, doc_id=doc_id)
    await pusher.update_node(node_id, node_type, fields)
