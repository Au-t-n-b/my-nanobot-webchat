"""SDUI DocStore (Milestone C): in-memory truth for Skill UI documents.

DocManager keeps a per-docId SduiDocument as the authoritative state during a run.
Patches are applied server-side before SSE emission so:
- Backend truth === Frontend truth (when patches are accepted)
- Disk I/O becomes checkpoint-only (run end / explicit checkpoint)
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from loguru import logger


class DocNotReadyError(RuntimeError):
    pass


class DocRevisionError(RuntimeError):
    pass


class DocApplyError(RuntimeError):
    pass


SduiDocument = dict[str, Any]
SduiPatch = dict[str, Any]


def _is_record(v: Any) -> bool:
    return v is not None and isinstance(v, dict)


def _node_id_of(node: Any) -> str | None:
    if not _is_record(node):
        return None
    v = node.get("id")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _walk_nodes(root: Any):
    """Yield every node dict in the SDUI tree (root + children + tabs)."""
    if not _is_record(root):
        return
    stack = [root]
    while stack:
        n = stack.pop()
        if not _is_record(n):
            continue
        yield n
        ch = n.get("children")
        if isinstance(ch, list):
            for item in reversed(ch):
                if _is_record(item):
                    stack.append(item)
        if n.get("type") == "Tabs":
            tabs = n.get("tabs")
            if isinstance(tabs, list):
                for tab in reversed(tabs):
                    if not _is_record(tab):
                        continue
                    tch = tab.get("children")
                    if isinstance(tch, list):
                        for item in reversed(tch):
                            if _is_record(item):
                                stack.append(item)


def _index_nodes_by_id(root: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for n in _walk_nodes(root):
        nid = _node_id_of(n)
        if nid:
            out[nid] = n
    return out


def _deep_merge_in_place(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for k, v in patch.items():
        # Guardrails (match frontend): do not patch structural fields.
        if k in ("children", "tabs"):
            continue
        if v is None:
            # Allow explicit null overwrite; frontend skips only undefined.
            target[k] = v
            continue
        tv = target.get(k)
        if isinstance(tv, dict) and isinstance(v, dict):
            _deep_merge_in_place(tv, v)
        else:
            target[k] = v


def _normalize_append_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [v for v in value if v is not None]
    return [value] if value is not None else []


def _apply_structural_ops(doc: SduiDocument, patch: SduiPatch) -> None:
    """Apply append/replace/remove in order; then caller rebuilds index."""
    ops = patch.get("ops") or []
    if not isinstance(ops, list):
        return
    root = doc.get("root")
    by_id = _index_nodes_by_id(root)
    for op in ops:
        if not _is_record(op):
            continue
        kind = op.get("op")
        if kind not in ("append", "replace", "remove"):
            continue
        target = op.get("target") if _is_record(op.get("target")) else {}
        node_id = target.get("nodeId") if isinstance(target.get("nodeId"), str) else ""
        node_id = node_id.strip()
        if not node_id:
            continue
        existing = by_id.get(node_id)
        if existing is None:
            continue

        if kind == "remove":
            # Match frontend M1 guardrails: ignore structural deletion.
            continue

        if kind == "replace":
            value = op.get("value")
            if not _is_record(value):
                continue
            # Frontend allows replace only if type matches.
            if value.get("type") != existing.get("type"):
                continue
            keep_id = _node_id_of(existing)
            existing.clear()
            existing.update(value)
            if keep_id and not _node_id_of(existing):
                existing["id"] = keep_id
            continue

        if kind == "append":
            field = target.get("field")
            if field not in ("children", "rows"):
                continue
            items = _normalize_append_value(op.get("value"))
            if not items:
                continue
            if field == "children":
                prev = existing.get("children")
                if not isinstance(prev, list):
                    prev = []
                    existing["children"] = prev
                is_partial = bool(patch.get("isPartial") is True)
                for item in items:
                    if not _is_record(item):
                        continue
                    if "type" not in item:
                        continue
                    if is_partial:
                        # Mirror frontend: partial nodes get a private marker for pulse.
                        item["_partial"] = True
                    prev.append(item)
                continue
            if field == "rows":
                # Only allow for DataGrid.
                if existing.get("type") != "DataGrid":
                    continue
                prev = existing.get("rows")
                if not isinstance(prev, list):
                    prev = []
                    existing["rows"] = prev
                prev.extend(items)
                continue


def _apply_merge_ops(doc: SduiDocument, patch: SduiPatch) -> None:
    ops = patch.get("ops") or []
    if not isinstance(ops, list):
        return
    root = doc.get("root")
    by_id = _index_nodes_by_id(root)
    for op in ops:
        if not _is_record(op):
            continue
        if op.get("op") != "merge":
            continue
        target = op.get("target") if _is_record(op.get("target")) else {}
        # Milestone D: meta merge (sync_state). This keeps UI state inside doc.meta.uiState.
        if target.get("by") == "meta":
            value = op.get("value")
            if not _is_record(value):
                continue
            meta = doc.get("meta")
            if not isinstance(meta, dict):
                meta = {}
                doc["meta"] = meta
            _deep_merge_in_place(meta, value)
            continue
        node_id = target.get("nodeId") if isinstance(target.get("nodeId"), str) else ""
        node_id = node_id.strip()
        if not node_id:
            continue
        existing = by_id.get(node_id)
        if existing is None:
            continue
        value = op.get("value")
        if not _is_record(value):
            continue
        # Enforce type match (match frontend).
        if value.get("type") != existing.get("type"):
            continue
        _deep_merge_in_place(existing, value)


@dataclass
class _DocEntry:
    doc: SduiDocument
    last_revision: int
    persist_path_hint: str | None = None


class DocManager:
    def __init__(
        self,
        *,
        workspace_root: Path,
        docid_to_datafile: Callable[[str], str | None] | None = None,
        max_docs: int = 32,
    ) -> None:
        self._workspace_root = Path(workspace_root).expanduser().resolve()
        self._docid_to_datafile = docid_to_datafile
        self._max_docs = int(max_docs) if max_docs and max_docs > 0 else 32
        self._docs: "OrderedDict[str, _DocEntry]" = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()

    def _touch_lru(self, doc_id: str) -> None:
        if doc_id in self._docs:
            self._docs.move_to_end(doc_id, last=True)

    async def _evict_if_needed(self) -> None:
        # Must be called under _global_lock.
        while len(self._docs) > self._max_docs:
            doc_id, _entry = self._docs.popitem(last=False)
            # keep lock map for now; clear_session_docs will be future hook.
            logger.debug("DocManager evicted docId={} (LRU)", doc_id)

    def _doc_lock(self, doc_id: str) -> asyncio.Lock:
        return self._locks[doc_id]

    async def ensure_doc(
        self,
        *,
        doc_id: str,
        initial_doc: SduiDocument,
        revision: int = 0,
        persist_path_hint: str | None = None,
    ) -> None:
        did = (doc_id or "").strip()
        if not did:
            raise ValueError("doc_id is required")
        if not _is_record(initial_doc):
            raise ValueError("initial_doc must be an object")
        async with self._doc_lock(did):
            async with self._global_lock:
                self._docs[did] = _DocEntry(doc=initial_doc, last_revision=int(revision), persist_path_hint=persist_path_hint)
                self._touch_lru(did)
                await self._evict_if_needed()

    async def has_doc(self, doc_id: str) -> bool:
        did = (doc_id or "").strip()
        if not did:
            return False
        async with self._global_lock:
            return did in self._docs

    async def get_snapshot(self, doc_id: str) -> tuple[int, SduiDocument]:
        did = (doc_id or "").strip()
        if not did:
            raise ValueError("doc_id is required")
        async with self._doc_lock(did):
            async with self._global_lock:
                entry = self._docs.get(did)
                if entry is None:
                    raise DocNotReadyError(f"doc not found: {did}")
                self._touch_lru(did)
                rev = entry.last_revision
                # Data safety: snapshot must be deep-copied.
                return rev, copy.deepcopy(entry.doc)

    async def try_get_snapshot(self, doc_id: str) -> tuple[int, SduiDocument] | None:
        try:
            return await self.get_snapshot(doc_id)
        except DocNotReadyError:
            return None

    async def apply_patch(self, patch: SduiPatch) -> tuple[int, SduiDocument]:
        if not _is_record(patch):
            raise ValueError("patch must be an object")
        doc_id = patch.get("docId")
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ValueError("patch.docId is required")
        did = doc_id.strip()
        revision = patch.get("revision")
        if not isinstance(revision, int):
            raise ValueError("patch.revision must be int")

        async with self._doc_lock(did):
            async with self._global_lock:
                entry = self._docs.get(did)
                if entry is None:
                    raise DocNotReadyError(f"doc not found: {did}")
                last = entry.last_revision
                if revision <= last:
                    raise DocRevisionError(f"stale revision: docId={did} revision={revision} last={last}")
                # Apply in-place for truth, but be careful about partial failures: we mutate only after successful ops.
                doc = entry.doc

            try:
                # Two-step apply:
                # 1) structural ops: append/replace/remove (remove is ignored by guardrail)
                _apply_structural_ops(doc, patch)
                # 2) rebuild id index implicitly inside merge apply
                _apply_merge_ops(doc, patch)
            except Exception as e:
                raise DocApplyError(str(e)) from e

            async with self._global_lock:
                entry = self._docs.get(did)
                if entry is None:
                    raise DocNotReadyError(f"doc evicted during apply: {did}")
                entry.last_revision = revision
                self._touch_lru(did)
                # Return deep-copied snapshot to avoid caller mutation.
                return revision, copy.deepcopy(entry.doc)

    def _resolve_persist_target(self, doc_id: str, persist_path_hint: str | None) -> Path | None:
        hint = (persist_path_hint or "").strip()
        if not hint and self._docid_to_datafile:
            hint = (self._docid_to_datafile(doc_id) or "").strip()
        if not hint:
            return None
        # Relative under workspace root; absolute path allowed only if still under workspace root.
        p = Path(hint).expanduser()
        target = (self._workspace_root / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            target.relative_to(self._workspace_root)
        except ValueError:
            # Do not allow writing outside workspace.
            return None
        return target

    async def checkpoint(self, doc_id: str) -> Path | None:
        did = (doc_id or "").strip()
        if not did:
            return None
        async with self._doc_lock(did):
            async with self._global_lock:
                entry = self._docs.get(did)
                if entry is None:
                    return None
                rev = entry.last_revision
                doc = copy.deepcopy(entry.doc)
                hint = entry.persist_path_hint
            target = self._resolve_persist_target(did, hint)
            if target is None:
                logger.debug("DocManager checkpoint skipped (no safe persist target) | docId={} rev={}", did, rev)
                return None

            target.parent.mkdir(parents=True, exist_ok=True)

            payload = json.dumps(doc, ensure_ascii=False, indent=2)

            async def _write() -> None:
                target.write_text(payload, encoding="utf-8")

            await asyncio.to_thread(_write)
            logger.info("DocManager checkpoint wrote | docId={} rev={} path={}", did, rev, str(target))
            return target

    async def on_run_end(self, *, doc_ids: list[str] | None = None) -> None:
        ids = [str(d).strip() for d in (doc_ids or []) if str(d).strip()]
        if not ids:
            return
        # Best-effort: checkpoint sequentially to reduce disk contention.
        for did in ids:
            try:
                await self.checkpoint(did)
            except Exception as e:
                logger.warning("DocManager checkpoint failed | docId={} | {}", did, e)

    async def clear_session_docs(self, session_id: str) -> None:
        """Reserved for future: clear docs associated with a session/thread."""
        _ = (session_id or "").strip()
        return

