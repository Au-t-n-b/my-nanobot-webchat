"""
Pydantic models for SDUI JSON — aligned with ``frontend/lib/sdui.ts``.

Use these models to build documents in Python; ``model_dump(mode="json")`` produces
keys compatible with the frontend ``parseSduiDocument`` validator.

Example::

    from nanobot.skills.sdui_builder import SduiDocument, SduiStackNode, SduiTextNode

    doc = SduiDocument(
        schemaVersion=1,
        root=SduiStackNode(children=[SduiTextNode(content="Hello")]),
    )
    Path("ui.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# ── Actions (discriminated by kind) ──────────────────────────────────────────


class SduiPostUserMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["post_user_message"] = "post_user_message"
    text: str


class SduiOpenPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["open_preview"] = "open_preview"
    path: str


SduiAction = Annotated[
    Union[SduiPostUserMessage, SduiOpenPreview],
    Field(discriminator="kind"),
]

SpacingToken = Literal["none", "xs", "sm", "md", "lg", "xl"]

# ── Column / KV helpers ──────────────────────────────────────────────────────


class DataGridColumn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str


class KeyValueItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    value: str


# ── Leaf nodes (no children) ─────────────────────────────────────────────────


class SduiDividerNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Divider"] = "Divider"
    id: str | None = None


class SduiTextNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Text"] = "Text"
    id: str | None = None
    content: str
    variant: Literal["title", "body", "muted", "mono"] | None = None


class SduiTextAreaNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["TextArea"] = "TextArea"
    id: str | None = None
    inputId: str
    label: str | None = None
    placeholder: str | None = None
    rows: int | None = None
    defaultValue: str | None = None


class SduiMarkdownNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Markdown"] = "Markdown"
    id: str | None = None
    content: str


class SduiBadgeNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Badge"] = "Badge"
    id: str | None = None
    text: str
    tone: Literal["default", "success", "warning", "danger"] | None = None


class SduiStatisticNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Statistic"] = "Statistic"
    id: str | None = None
    title: str
    value: str | int | float


class SduiKeyValueListNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["KeyValueList"] = "KeyValueList"
    id: str | None = None
    items: list[KeyValueItem]


class SduiTableNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Table"] = "Table"
    id: str | None = None
    headers: list[str] | None = None
    rows: list[list[str]]


class SduiDataGridNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["DataGrid"] = "DataGrid"
    id: str | None = None
    columns: list[DataGridColumn]
    rows: list[dict[str, Any]]
    editable: bool | None = None
    submitLabel: str | None = None
    submitActionPrefix: str | None = None


class SduiButtonNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Button"] = "Button"
    id: str | None = None
    label: str
    variant: Literal["primary", "secondary", "ghost"] | None = None
    action: SduiPostUserMessage | SduiOpenPreview


class SduiLinkNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Link"] = "Link"
    id: str | None = None
    label: str
    href: str | None = None
    action: SduiPostUserMessage | SduiOpenPreview | None = None


class SduiStackNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Stack"] = "Stack"
    id: str | None = None
    gap: SpacingToken | None = None
    children: list["SduiNode"] | None = None


class SduiCardNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Card"] = "Card"
    id: str | None = None
    title: str | None = None
    children: list["SduiNode"] | None = None


class SduiRowNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Row"] = "Row"
    id: str | None = None
    gap: SpacingToken | None = None
    align: Literal["start", "center", "end", "stretch", "baseline"] | None = None
    wrap: bool | None = None
    children: list["SduiNode"] | None = None


SduiTabIconName = Literal[
    "terminal",
    "clipboardCheck",
    "alertTriangle",
    "image",
    "fileText",
    "layoutDashboard",
    "circle",
]


class SduiTabPanel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    icon: SduiTabIconName | None = None
    children: list["SduiNode"] | None = None


class SduiTabsNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Tabs"] = "Tabs"
    id: str | None = None
    tabs: list[SduiTabPanel]
    defaultTabId: str | None = None


class SduiStepperStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    status: Literal["waiting", "running", "done", "error"]


class SduiStepperNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["Stepper"] = "Stepper"
    id: str | None = None
    steps: list[SduiStepperStep]
    orientation: Literal["horizontal", "vertical"] | None = None


SduiNode = Annotated[
    Union[
        SduiStackNode,
        SduiCardNode,
        SduiRowNode,
        SduiDividerNode,
        SduiTabsNode,
        SduiStepperNode,
        SduiTextNode,
        SduiTextAreaNode,
        SduiMarkdownNode,
        SduiBadgeNode,
        SduiStatisticNode,
        SduiKeyValueListNode,
        SduiTableNode,
        SduiDataGridNode,
        SduiButtonNode,
        SduiLinkNode,
    ],
    Field(discriminator="type"),
]

SduiNodeAdapter: TypeAdapter[SduiNode] = TypeAdapter(SduiNode)

SduiNodeTypeAlias = SduiNode  # concrete alias for model_rebuild namespace


class SduiDocument(BaseModel):
    """Root document matching ``SduiDocument`` in ``frontend/lib/sdui.ts``."""

    model_config = ConfigDict(extra="ignore")

    schemaVersion: int
    type: Literal["SduiDocument"] = "SduiDocument"
    root: SduiNodeTypeAlias
    meta: dict[str, Any] | None = None


# Resolve forward references for recursive ``children``
_ns = {"SduiNode": SduiNode}
for _m in (SduiStackNode, SduiCardNode, SduiRowNode, SduiTabPanel, SduiTabsNode, SduiDocument):
    _m.model_rebuild(_types_namespace=_ns)


def dump_sdui_json(doc: SduiDocument) -> dict[str, Any]:
    """Serialize to JSON-compatible dict (camelCase keys preserved)."""
    return doc.model_dump(mode="json")


def validate_sdui_json(data: Any) -> SduiDocument:
    """Parse arbitrary JSON object into a validated ``SduiDocument``."""
    return SduiDocument.model_validate(data)
