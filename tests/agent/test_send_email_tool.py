import pytest
from unittest.mock import MagicMock
from nanobot.agent.tools.email import SendEmailTool, OutlookSender
from nanobot.config.schema import EmailToolConfig
from pathlib import Path


def test_tool_metadata():
    tool = SendEmailTool(config=EmailToolConfig(), workspace=Path("/tmp"))
    assert tool.name == "send_email"
    assert "email" in tool.description.lower()
    schema = tool.parameters
    assert "to" in schema["properties"]
    assert "subject" in schema["properties"]
    assert "body_html" in schema["properties"]
    assert "body_file" in schema["properties"]
    assert "body_text" in schema["properties"]
    assert "cc" in schema["properties"]
    assert "bcc" in schema["properties"]
    assert "attachments" in schema["properties"]
    assert schema["required"] == ["to", "subject"]


@pytest.mark.asyncio
async def test_rejects_external_domain():
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=Path("/tmp"))
    result = await tool.execute(
        to=["evil@gmail.com"],
        subject="test",
        body_html="<p>hello</p>",
    )
    assert "blocked" in result.lower() or "not allowed" in result.lower()


@pytest.mark.asyncio
async def test_rejects_path_traversal():
    cfg = EmailToolConfig(enable=True)
    tool = SendEmailTool(config=cfg, workspace=Path("/workspace"))
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_html="<p>hello</p>",
        attachments=["../../etc/passwd"],
    )
    assert "outside workspace" in result.lower() or "blocked" in result.lower()


@pytest.mark.asyncio
async def test_send_success(tmp_path):
    att = tmp_path / "report.xlsx"
    att.write_text("fake")
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    mock_sender.send = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_html="<p>hello</p>",
        attachments=[str(att)],
    )
    assert "sent" in result.lower() or "success" in result.lower()
    mock_sender.send.assert_called_once()


@pytest.mark.asyncio
async def test_rejects_empty_recipients():
    cfg = EmailToolConfig(enable=True)
    tool = SendEmailTool(config=cfg, workspace=Path("/tmp"))
    result = await tool.execute(to=[], subject="test", body_html="<p>hi</p>")
    assert "no recipients" in result.lower()


@pytest.mark.asyncio
async def test_rejects_missing_attachment(tmp_path):
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=tmp_path)
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_html="<p>hello</p>",
        attachments=[str(tmp_path / "nonexistent.pdf")],
    )
    assert "not found" in result.lower()


# --- body_file tests ---

@pytest.mark.asyncio
async def test_body_file_reads_html_content(tmp_path):
    html_file = tmp_path / "body.html"
    html_file.write_text("<h1>Hello</h1>", encoding="utf-8")
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_file=str(html_file),
    )
    assert "sent" in result.lower()
    call_kwargs = mock_sender.send.call_args
    assert "<h1>Hello</h1>" in call_kwargs.kwargs["body_html"]


@pytest.mark.asyncio
async def test_body_file_txt_wraps_pre(tmp_path):
    txt_file = tmp_path / "body.txt"
    txt_file.write_text("plain text content", encoding="utf-8")
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_file=str(txt_file),
    )
    assert "sent" in result.lower()
    call_kwargs = mock_sender.send.call_args
    assert "<pre>" in call_kwargs.kwargs["body_html"]
    assert "plain text content" in call_kwargs.kwargs["body_html"]


@pytest.mark.asyncio
async def test_body_file_outside_workspace(tmp_path):
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=tmp_path)
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_file="/etc/passwd",
    )
    assert "blocked" in result.lower() or "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_body_file_not_found(tmp_path):
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=tmp_path)
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_file=str(tmp_path / "missing.html"),
    )
    assert "not found" in result.lower()


# --- CC/BCC tests ---

@pytest.mark.asyncio
async def test_cc_bcc_domain_validation():
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=Path("/tmp"))
    result = await tool.execute(
        to=["user@huawei.com"],
        cc=["external@gmail.com"],
        subject="test",
        body_html="<p>hi</p>",
    )
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_bcc_domain_validation():
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=Path("/tmp"))
    result = await tool.execute(
        to=["user@huawei.com"],
        bcc=["external@qq.com"],
        subject="test",
        body_html="<p>hi</p>",
    )
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_cc_bcc_sent_correctly(tmp_path):
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    result = await tool.execute(
        to=["a@huawei.com"],
        cc=["b@huawei.com"],
        bcc=["c@huawei.com"],
        subject="test",
        body_html="<p>hi</p>",
    )
    assert "sent" in result.lower()
    assert "CC" in result
    assert "BCC" in result
    call_kwargs = mock_sender.send.call_args
    assert call_kwargs.kwargs["cc"] == ["b@huawei.com"]
    assert call_kwargs.kwargs["bcc"] == ["c@huawei.com"]


# --- body priority tests ---

@pytest.mark.asyncio
async def test_body_priority_file_over_html(tmp_path):
    html_file = tmp_path / "body.html"
    html_file.write_text("<b>from file</b>", encoding="utf-8")
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_file=str(html_file),
        body_html="<p>inline html</p>",
    )
    call_kwargs = mock_sender.send.call_args
    assert "<b>from file</b>" in call_kwargs.kwargs["body_html"]


@pytest.mark.asyncio
async def test_body_priority_html_over_text(tmp_path):
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_html="<p>html body</p>",
        body_text="plain text",
    )
    call_kwargs = mock_sender.send.call_args
    assert call_kwargs.kwargs["body_html"] == "<p>html body</p>"
    assert call_kwargs.kwargs["body_text"] == ""


@pytest.mark.asyncio
async def test_body_text_only(tmp_path):
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    mock_sender = MagicMock()
    tool = SendEmailTool(config=cfg, workspace=tmp_path, sender=mock_sender)
    await tool.execute(
        to=["user@huawei.com"],
        subject="test",
        body_text="just plain",
    )
    call_kwargs = mock_sender.send.call_args
    assert call_kwargs.kwargs["body_text"] == "just plain"
    assert call_kwargs.kwargs["body_html"] == ""


@pytest.mark.asyncio
async def test_no_body_returns_error():
    cfg = EmailToolConfig(enable=True, allowed_domains=["huawei.com"])
    tool = SendEmailTool(config=cfg, workspace=Path("/tmp"))
    result = await tool.execute(
        to=["user@huawei.com"],
        subject="test",
    )
    assert "error" in result.lower()
    assert "body" in result.lower()
