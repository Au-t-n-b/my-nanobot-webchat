"""recall_context tool: search archived conversation history."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool

_MAX_RESPONSE_CHARS = 2000


class RecallContextTool(Tool):
    """Search compacted/archived conversation history via SQLite."""

    def __init__(self, archive: Any):
        self._archive = archive
        self._conversation_id: str | None = None

    def set_context(self, conversation_id: str) -> None:
        """Set the current conversation_id for session-scoped searches."""
        self._conversation_id = conversation_id

    @property
    def name(self) -> str:
        return "recall_context"

    @property
    def description(self) -> str:
        return (
            "搜索历史对话中的压缩/归档内容。"
            "keyword 模式按关键词搜索，range 模式按 range_id 获取完整摘要。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["keyword", "range"],
                    "description": "keyword: 按关键词搜索; range: 按 range_id 获取完整摘要",
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词（keyword 模式必填）",
                },
                "range_id": {
                    "type": "integer",
                    "description": "归档范围 ID（range 模式必填）",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "返回结果数量上限",
                },
            },
            "required": ["mode"],
        }

    async def execute(self, **kwargs: Any) -> str:
        mode = kwargs.get("mode", "")
        if mode == "keyword":
            return self._keyword_search(kwargs)
        elif mode == "range":
            return self._range_get(kwargs)
        return "错误: mode 必须是 'keyword' 或 'range'"

    def _keyword_search(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 10)
        # conversation_id comes from the session — injected at integration time
        conv_id = self._conversation_id or kwargs.get("_conversation_id", "")
        if not query:
            return "错误: keyword 模式需要提供 query 参数"

        results = self._archive.search_by_keyword(conv_id, query, limit)
        if not results:
            return f"未找到匹配 '{query}' 的消息。"

        lines = [f"找到 {len(results)} 条匹配消息:\n"]
        total_chars = 0
        for r in results:
            line = f"[Range #{r['range_id']}, msg_{r['msg_idx']}] {r['role']}: \"{r['preview']}\""
            if total_chars + len(line) > _MAX_RESPONSE_CHARS:
                lines.append("\n... 结果过多，已截断。使用更精确的关键词缩小范围。")
                break
            lines.append(line)
            total_chars += len(line)

        lines.append(f"\n使用 recall_context(mode=\"range\", range_id={results[0]['range_id']}) 可获取完整摘要。")
        return "\n".join(lines)

    def _range_get(self, kwargs: dict[str, Any]) -> str:
        range_id = kwargs.get("range_id")
        if range_id is None:
            return "错误: range 模式需要提供 range_id 参数"

        data = self._archive.get_range(int(range_id))
        if not data:
            return f"未找到 range #{range_id}。"

        lines = [f"Range #{range_id} 摘要:"]
        if data.get("summary"):
            lines.append(data["summary"])
        else:
            lines.append("(无摘要)")

        lines.append(f"\n原始消息共 {data.get('messages_count', '?')} 条:")
        for msg in data.get("messages", []):
            name_suffix = f"/{msg['name']}" if msg.get("name") else ""
            lines.append(f"  msg_{msg['msg_idx']} [{msg['role']}{name_suffix}]: \"{msg['preview']}\"")

        lines.append('\n使用 recall_context(mode="keyword", query="关键词") 搜索具体消息内容。')
        return "\n".join(lines)
