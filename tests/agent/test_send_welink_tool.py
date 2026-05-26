import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from nanobot.agent.tools.welink import SendWelinkTool, format_table, _build_plain_table
from nanobot.config.schema import WelinkToolConfig


def test_tool_metadata():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_abc")
    tool = SendWelinkTool(config=cfg)
    assert tool.name == "send_welink"
    assert "welink" in tool.description.lower() or "XiaoLuban" in tool.description
    schema = tool.parameters
    assert "content" in schema["properties"]
    assert "receiver" in schema["properties"]
    assert "format" in schema["properties"]
    assert "table_data" in schema["properties"]


def test_description_mentions_rich_text():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_abc")
    tool = SendWelinkTool(config=cfg)
    desc = tool.description
    assert "span" in desc.lower()
    assert "color" in desc.lower()
    assert "bold" in desc.lower()


@pytest.mark.asyncio
async def test_missing_auth():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="")
    tool = SendWelinkTool(config=cfg)
    with patch.dict("os.environ", {}, clear=True):
        result = await tool.execute(content="hello", receiver="12345")
    assert "auth" in result.lower()


@pytest.mark.asyncio
async def test_send_success():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token123")
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "ok"
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        result = await tool.execute(content="test message", receiver="944015505503649831")
    assert "sent" in result.lower()
    mock_req.post.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limit_per_minute():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token", rate_limit_per_minute=2)
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        await tool.execute(content="msg1", receiver="r1")
        await tool.execute(content="msg2", receiver="r1")
        result = await tool.execute(content="msg3", receiver="r1")
    assert "rate" in result.lower() or "limit" in result.lower()


@pytest.mark.asyncio
async def test_daily_rate_limit():
    cfg = WelinkToolConfig(
        enable=True, xiaoluban_auth="j00_token",
        rate_limit_per_minute=100, rate_limit_per_day=2,
    )
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        await tool.execute(content="msg1", receiver="r1")
        await tool.execute(content="msg2", receiver="r1")
        result = await tool.execute(content="msg3", receiver="r1")
    assert "daily" in result.lower()


@pytest.mark.asyncio
async def test_daily_limit_resets_on_new_day():
    cfg = WelinkToolConfig(
        enable=True, xiaoluban_auth="j00_token",
        rate_limit_per_minute=100, rate_limit_per_day=1,
    )
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        await tool.execute(content="msg1", receiver="r1")

        # Simulate day change
        tool._daily_date = date(2020, 1, 1)
        result = await tool.execute(content="msg2", receiver="r1")
    assert "sent" in result.lower()


@pytest.mark.asyncio
async def test_empty_content():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    result = await tool.execute(content="", receiver="12345")
    assert "empty" in result.lower()


@pytest.mark.asyncio
async def test_empty_receiver():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    result = await tool.execute(content="hello", receiver="")
    assert "receiver" in result.lower()


@pytest.mark.asyncio
async def test_env_auth_takes_priority():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="config_token")
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    with patch.dict("os.environ", {"XIAOLUBAN_AUTH": "env_token"}, clear=False):
        with patch("nanobot.agent.tools.welink.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            await tool.execute(content="test", receiver="r1")
            call_data = mock_req.post.call_args
            assert call_data.kwargs["json"]["auth"] == "env_token"


@pytest.mark.asyncio
async def test_http_error():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=False, status_code=403, text="Invalid Certification")
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        result = await tool.execute(content="test", receiver="r1")
    assert "403" in result or "error" in result.lower()


# --- table format tests ---

@pytest.mark.asyncio
async def test_table_format():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        result = await tool.execute(
            receiver="r1",
            format="table",
            table_data={"headers": ["Name", "Status"], "rows": [["A", "OK"]]},
        )
    assert "sent" in result.lower()
    assert "table" in result.lower()
    sent_content = mock_req.post.call_args.kwargs["json"]["content"]
    assert "Consolas" in sent_content
    assert "Name" in sent_content
    assert "OK" in sent_content


@pytest.mark.asyncio
async def test_table_missing_data():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    result = await tool.execute(receiver="r1", format="table")
    assert "error" in result.lower()
    assert "table_data" in result.lower()


@pytest.mark.asyncio
async def test_content_plus_table():
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        await tool.execute(
            content="Report Title",
            receiver="r1",
            format="table",
            table_data={"headers": ["Col"], "rows": [["Val"]]},
        )
    sent_content = mock_req.post.call_args.kwargs["json"]["content"]
    assert "Report Title" in sent_content
    assert "Consolas" in sent_content


@pytest.mark.asyncio
async def test_rich_text_passthrough():
    """Span tags in content should be sent as-is, not escaped."""
    cfg = WelinkToolConfig(enable=True, xiaoluban_auth="j00_token")
    tool = SendWelinkTool(config=cfg)
    mock_resp = MagicMock(ok=True, text="ok")
    rich_content = '<span style="color:green;font-weight:bold;">PASS</span>'
    with patch("nanobot.agent.tools.welink.requests") as mock_req:
        mock_req.post.return_value = mock_resp
        await tool.execute(content=rich_content, receiver="r1")
    sent_content = mock_req.post.call_args.kwargs["json"]["content"]
    assert sent_content == rich_content


# --- format_table unit tests ---

def test_format_table_output():
    result = format_table(["A", "B"], [["1", "2"]])
    assert "Consolas" in result
    assert "A" in result
    assert "1" in result


def test_build_plain_table():
    result = _build_plain_table(["Name", "Value"], [["x", "y"]])
    assert "Name" in result
    assert "x" in result
    assert "+" in result


def test_table_without_prettytable():
    """Ensure _build_plain_table works standalone as fallback."""
    result = _build_plain_table(["H1", "H2"], [["a", "b"], ["c", "d"]])
    lines = result.split("\n")
    assert len(lines) >= 5  # separator, header, separator, 2 rows, separator
