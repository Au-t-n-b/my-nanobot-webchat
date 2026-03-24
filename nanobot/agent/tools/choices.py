"""Tool for asking user to pick one option."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool


class PresentChoicesTool(Tool):
    """Return normalized choices for UI modal rendering."""

    @property
    def name(self) -> str:
        return "present_choices"

    @property
    def description(self) -> str:
        return "Present multiple choices to user and wait for selection."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["label", "value"],
                    },
                    "minItems": 1,
                },
                "title": {"type": "string"},
            },
            "required": ["choices"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        choices = kwargs.get("choices", [])
        if not isinstance(choices, list):
            return "Error: choices must be an array."
        normalized = []
        for c in choices:
            if not isinstance(c, dict):
                continue
            label = str(c.get("label", "")).strip()
            value = str(c.get("value", "")).strip()
            if label and value:
                normalized.append({"label": label, "value": value})
        if not normalized:
            return "Error: no valid choices provided."
        return {"choices": normalized, "title": str(kwargs.get("title", ""))}
