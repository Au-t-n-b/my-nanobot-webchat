"""Email sending tool with provider abstraction."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.config.schema import EmailToolConfig


_HTML_EXTENSIONS = {".html", ".htm"}


class EmailSender(ABC):
    """Abstract email sender — extend for SMTP, Graph API, etc."""

    @abstractmethod
    def send(
        self,
        to: list[str],
        subject: str,
        body_html: str = "",
        body_text: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[str] | None = None,
    ) -> None: ...


class OutlookSender(EmailSender):
    """Send via local Outlook COM (Windows only, requires pywin32)."""

    def send(
        self,
        to: list[str],
        subject: str,
        body_html: str = "",
        body_text: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[str] | None = None,
    ) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except Exception:
            outlook = win32com.client.Dispatch("Outlook.Application")

        mail = outlook.CreateItem(0)
        mail.To = ";".join(to)
        mail.Subject = subject
        if cc:
            mail.CC = ";".join(cc)
        if bcc:
            mail.BCC = ";".join(bcc)
        if body_html:
            mail.HTMLBody = body_html
        elif body_text:
            mail.Body = body_text
        for path in attachments or []:
            mail.Attachments.Add(os.path.abspath(path))
        mail.Send()


class SendEmailTool(Tool):
    """Agent tool: send email via Outlook COM."""

    def __init__(
        self,
        config: EmailToolConfig,
        workspace: Path,
        sender: EmailSender | None = None,
    ):
        self._config = config
        self._workspace = workspace.resolve()
        self._sender = sender

    @property
    def name(self) -> str:
        return "send_email"

    @property
    def description(self) -> str:
        domains = ", ".join(self._config.allowed_domains)
        return (
            "Send an email via Outlook with optional file attachments. "
            f"Recipients (to/cc/bcc) MUST have one of these domains: {domains}. "
            "Body priority: body_file > body_html > body_text. "
            "Use body_file to send an existing file as the email body without reading it first."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of recipient email addresses",
                },
                "cc": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional CC recipients",
                },
                "bcc": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional BCC recipients",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body_file": {
                    "type": "string",
                    "description": (
                        "File path whose content becomes the email body. "
                        ".html/.htm files are sent as HTML; other files are wrapped in <pre>. "
                        "Must be within workspace. Takes priority over body_html/body_text."
                    ),
                },
                "body_html": {
                    "type": "string",
                    "description": "Email body in HTML format",
                },
                "body_text": {
                    "type": "string",
                    "description": "Plain-text email body (lowest priority)",
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of file paths to attach (must be within workspace)",
                },
            },
            "required": ["to", "subject"],
        }

    def _validate_domains(self, recipients: list[str]) -> str | None:
        allowed = {d.lower() for d in self._config.allowed_domains}
        for addr in recipients:
            domain = addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""
            if domain not in allowed:
                return (
                    f"Recipient '{addr}' blocked: domain '{domain}' "
                    f"not in allowed list {sorted(allowed)}"
                )
        return None

    def _validate_path(self, raw: str, *, must_exist: bool = True) -> str | None:
        """Validate a single path is within the workspace (and optionally exists)."""
        resolved = Path(raw).resolve()
        try:
            resolved.relative_to(self._workspace)
        except ValueError:
            return (
                f"Path '{raw}' blocked: outside workspace "
                f"({self._workspace})"
            )
        if must_exist and not resolved.is_file():
            return f"Path '{raw}' not found"
        return None

    def _validate_attachments(self, paths: list[str]) -> str | None:
        for raw in paths:
            if err := self._validate_path(raw):
                return err
        return None

    def _resolve_body(
        self, body_file: str, body_html: str, body_text: str,
    ) -> tuple[str, str, str | None]:
        """Return (html, plain, error).  Priority: body_file > body_html > body_text."""
        if body_file:
            if err := self._validate_path(body_file):
                return "", "", f"body_file error: {err}"
            resolved = Path(body_file).resolve()
            try:
                content = resolved.read_text(encoding="utf-8")
            except Exception as e:
                return "", "", f"body_file read error: {e}"
            if resolved.suffix.lower() in _HTML_EXTENSIONS:
                return content, "", None
            return f"<pre>{content}</pre>", "", None
        if body_html:
            return body_html, "", None
        if body_text:
            return "", body_text, None
        return "", "", "No email body provided (use body_file, body_html, or body_text)."

    async def execute(self, **kwargs: Any) -> str:
        to: list[str] = kwargs.get("to", [])
        cc: list[str] = kwargs.get("cc") or []
        bcc: list[str] = kwargs.get("bcc") or []
        subject: str = kwargs.get("subject", "")
        body_file: str = kwargs.get("body_file", "")
        body_html: str = kwargs.get("body_html", "")
        body_text: str = kwargs.get("body_text", "")
        attachments: list[str] = kwargs.get("attachments") or []

        if not to:
            return "Error: no recipients specified."

        all_recipients = to + cc + bcc
        if err := self._validate_domains(all_recipients):
            return f"Error: {err}"
        if attachments and (err := self._validate_attachments(attachments)):
            return f"Error: {err}"

        html, plain, body_err = self._resolve_body(body_file, body_html, body_text)
        if body_err:
            return f"Error: {body_err}"

        sender = self._sender
        if sender is None:
            try:
                sender = OutlookSender()
            except Exception as e:
                return f"Error: failed to initialize Outlook sender: {e}"

        try:
            abs_attachments = [str(Path(p).resolve()) for p in attachments]
            sender.send(
                to, subject,
                body_html=html,
                body_text=plain,
                cc=cc or None,
                bcc=bcc or None,
                attachments=abs_attachments,
            )
            parts = []
            if cc:
                parts.append(f"CC: {', '.join(cc)}")
            if bcc:
                parts.append(f"BCC: {', '.join(bcc)}")
            if attachments:
                parts.append(f"{len(attachments)} attachment(s)")
            extra = f" ({'; '.join(parts)})" if parts else ""
            return f"Email sent to {', '.join(to)}{extra}."
        except Exception as e:
            logger.error("send_email failed: {}", e)
            return f"Error sending email: {e}"
