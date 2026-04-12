"""Module contract validation helpers for reusable module templates."""

from __future__ import annotations

from typing import Any

REQUIRED_MODULE_FIELDS: tuple[str, ...] = ("moduleId", "flow", "docId", "dataFile")
REQUIRED_DASHBOARD_NODE_IDS: frozenset[str] = frozenset(
    {"stepper-main", "summary-text", "artifacts", "uploaded-files"}
)


def validate_module_contract(raw: dict[str, Any]) -> dict[str, Any]:
    missing = [
        field
        for field in REQUIRED_MODULE_FIELDS
        if not str(raw.get(field) or "").strip()
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"module.json missing required fields: {joined}")

    uploads = raw.get("uploads")
    if isinstance(uploads, list):
        for upload in uploads:
            if not isinstance(upload, dict):
                raise ValueError("upload config must be a JSON object")
            if not str(upload.get("save_relative_dir") or "").strip():
                raise ValueError("upload config missing save_relative_dir")

    return raw


def validate_dashboard_contract(document: dict[str, Any]) -> None:
    seen_ids: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node_id = str(node.get("id") or "").strip()
            if node_id:
                seen_ids.add(node_id)
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    missing = sorted(REQUIRED_DASHBOARD_NODE_IDS - seen_ids)
    if missing:
        raise ValueError(f"dashboard.json missing required node ids: {', '.join(missing)}")
