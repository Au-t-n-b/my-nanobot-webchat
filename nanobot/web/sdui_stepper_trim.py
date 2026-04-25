"""Strip SDUI Stepper nodes from dashboard documents (opt-out defaults per module)."""

from __future__ import annotations

import copy
from typing import Any


def is_job_management_module_id(module_id: str) -> bool:
    return (module_id or "").strip().replace("-", "_") == "job_management"


def is_job_management_synthetic_path(synthetic_path: str) -> bool:
    p = (synthetic_path or "").replace("\\", "/").lower()
    return "/skills/job_management/" in p or "job_management/data/dashboard" in p


def filter_dashboard_patch_ops_drop_stepper(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove merge ops that update or insert the main SDUI Stepper (legacy driver 仍可能 emit)。"""
    out: list[dict[str, Any]] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        if op.get("op") != "merge":
            out.append(op)
            continue
        target = op.get("target")
        if isinstance(target, dict) and target.get("by") == "id":
            nid = str(target.get("nodeId") or "").strip()
            if nid == "stepper-main":
                continue
        value = op.get("value")
        if isinstance(value, dict) and value.get("type") == "Stepper":
            continue
        out.append(op)
    return out


def strip_sdui_stepper_nodes(document: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove nodes with type ``Stepper`` from ``children`` lists."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out = dict(node)
            ch = out.get("children")
            if isinstance(ch, list):
                new_ch: list[Any] = []
                for c in ch:
                    if isinstance(c, dict) and c.get("type") == "Stepper":
                        continue
                    new_ch.append(walk(c))
                out["children"] = new_ch
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    doc = copy.deepcopy(document)
    root = doc.get("root")
    if root is not None:
        doc["root"] = walk(root)
    return doc
