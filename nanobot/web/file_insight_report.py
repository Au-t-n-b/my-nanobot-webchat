"""Structured report for preview file insight (Phase 3 agentic preview)."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


class FileInsightReport(BaseModel):
    """LLM output schema — must match frontend `FileInsightReport` type."""

    file_type_guess: str = Field(..., description="类型猜测，如 PE / UTF-8 text / gzip")
    summary: str
    risk_level: Literal["safe", "warning", "danger"]
    extracted_snippets: list[str] = Field(default_factory=list, max_length=20)
    next_action_suggestion: str


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json_object_text(raw: str) -> str:
    """Strip optional markdown fences and surrounding whitespace."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty model output")
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text


def parse_file_insight_report_from_llm_text(raw: str) -> FileInsightReport:
    """Parse and validate assistant final message as ``FileInsightReport``."""
    blob = extract_json_object_text(raw)
    try:
        data: Any = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid json: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("json root must be an object")
    return FileInsightReport.model_validate(data)
