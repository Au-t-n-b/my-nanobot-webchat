"""Tool result persistence: replace simple truncation with file-backed references."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.schema import PersistedOutputConfig
from nanobot.utils.helpers import ensure_dir


class PersistedOutputManager:
    """Manages tool result persistence to disk with reference tags."""

    def __init__(self, workspace: Path, config: PersistedOutputConfig | None = None):
        self.config = config or PersistedOutputConfig()
        self.results_dir = ensure_dir(workspace / self.config.results_dir)
        self._decision_cache: dict[str, bool] = {}

    def should_persist(self, content: str, tool_name: str, tool_call_id: str) -> bool:
        """Decide whether to persist. Decision is frozen per tool_call_id."""
        if tool_call_id in self._decision_cache:
            return self._decision_cache[tool_call_id]

        if tool_name in self.config.exempt_tools:
            self._decision_cache[tool_call_id] = False
            return False

        result = len(content) > self.config.size_threshold
        self._decision_cache[tool_call_id] = result
        return result

    def persist(
        self,
        content: str,
        tool_call_id: str,
        tool_name: str,
    ) -> str:
        """Write full content to disk, return preview with reference tag."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = tool_name.replace("/", "_").replace("\\", "_")
        filename = f"{safe_name}_{tool_call_id[:8]}_{ts}.txt"
        filepath = self.results_dir / filename
        filepath.write_text(content, encoding="utf-8")

        head = content[: self.config.preview_head]
        tail = content[-self.config.preview_tail :] if self.config.preview_tail > 0 else ""
        tag = (
            f"<persisted-output file='{self.config.results_dir}/{filename}'"
            f" size='{len(content)}' tool='{tool_name}'"
            f" tool_call_id='{tool_call_id}'/>"
        )
        preview = f"{head}\n{tag}\n{tail}"
        logger.debug("Persisted tool result: {} ({} chars) → {}", tool_call_id[:8], len(content), filename)
        return preview

    def apply_aggregate_budget(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Check total tool result size against aggregate budget.

        If exceeded, persist the largest results until total is within budget.
        Each result dict should have: tool_call_id, tool_name, content.
        Returns the (possibly modified) results list.
        """
        total = sum(len(r.get("content", "")) for r in results)
        if total <= self.config.aggregate_budget:
            return results

        # Sort by size descending, persist largest first
        indexed = [(i, len(r.get("content", "")), r) for i, r in enumerate(results)]
        indexed.sort(key=lambda x: x[1], reverse=True)

        modified = list(results)
        for idx, size, result in indexed:
            if total <= self.config.aggregate_budget:
                break
            tool_call_id = result.get("tool_call_id", "")
            tool_name = result.get("tool_name", "")
            content = result.get("content", "")
            if not content or not tool_call_id:
                continue

            old_len = len(content)
            preview = self.persist(content, tool_call_id, tool_name)
            modified[idx] = {**result, "content": preview}
            total -= old_len - len(preview)
            logger.debug("Aggregate budget: persisted {} ({} → {} chars)", tool_call_id[:8], old_len, len(preview))

        return modified

    def cleanup_expired(self) -> int:
        """Delete files in results_dir older than retention_days. Returns count deleted."""
        if not self.results_dir.exists():
            return 0

        cutoff = time.time() - self.config.retention_days * 86400
        deleted = 0
        for f in self.results_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        if deleted:
            logger.info("Cleaned up {} expired tool-result files", deleted)
        return deleted

    def truncate_inline(self, content: str, max_chars: int = 2000) -> str:
        """Simple truncation for exempt tools (no persistence)."""
        if len(content) <= max_chars:
            return content
        half = max_chars // 2
        return (
            content[:half]
            + f"\n... [truncated, {len(content)} chars total, "
            f"showing first {half} and last {half}]\n"
            + content[-half:]
        )
