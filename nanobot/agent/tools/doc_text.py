"""Doc/DOCX text extraction tool for controlled hybrid subtasks."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from nanobot.agent.tools.base import Tool


def _is_under(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def _normalize_ws_path(path: str, workspace: Path) -> Path:
    p = Path(str(path or "")).expanduser()
    if not p.is_absolute():
        p = workspace / p
    resolved = p.resolve()
    if not _is_under(resolved, workspace):
        raise PermissionError(f"path is outside workspace: {path}")
    return resolved


def _strip_xml_text(xml_bytes: bytes) -> str:
    # Best-effort XML parse; fall back to tag strip.
    try:
        root = ET.fromstring(xml_bytes)
        text = "".join(root.itertext())
        return re.sub(r"[ \t]+\n", "\n", text).strip()
    except Exception:
        s = xml_bytes.decode("utf-8", errors="ignore")
        s = re.sub(r"<[^>]+>", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        # Core body.
        xml = z.read("word/document.xml")
    return _strip_xml_text(xml)


def extract_doc_text_via_soffice(path: Path, *, workspace: Path, timeout_s: int = 30) -> str:
    # Requires LibreOffice (soffice) installed and in PATH.
    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    if not soffice:
        raise RuntimeError("no_converter: missing soffice (LibreOffice) in PATH")
    with tempfile.TemporaryDirectory(prefix="nanobot-doc-", dir=str(workspace)) as td:
        out_dir = Path(td).resolve()
        # Convert to plain text.
        # Note: On Windows, soffice may still spawn; use --headless and wait.
        cmd = [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(out_dir),
            str(path),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s, check=False)
        txt = out_dir / (path.stem + ".txt")
        if not txt.is_file():
            raise RuntimeError("convert_failed: soffice did not produce txt output")
        return txt.read_text(encoding="utf-8", errors="ignore").strip()


class ExtractDocTextTool(Tool):
    """Extract text from `.docx` (native) and `.doc` (best-effort via LibreOffice)."""

    def __init__(self, workspace: Path):
        self._workspace = workspace.resolve()

    @property
    def name(self) -> str:
        return "extract_doc_text"

    @property
    def description(self) -> str:
        return (
            "Extract readable text from a .doc/.docx file within the workspace. "
            ".docx is parsed natively; .doc requires LibreOffice (soffice) and is best-effort."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative path to .doc/.docx"},
                "max_chars": {"type": "integer", "description": "Max chars to return", "default": 12000},
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        raw = str(kwargs.get("path") or "").strip()
        if not raw:
            return "Error: missing path"
        max_chars = int(kwargs.get("max_chars") or 12000)
        max_chars = max(200, min(max_chars, 200_000))

        p = _normalize_ws_path(raw, self._workspace)
        if not p.is_file():
            return f"Error: file not found: {raw}"

        suf = p.suffix.lower()
        try:
            if suf == ".docx":
                text = extract_docx_text(p)
            elif suf == ".doc":
                # Best-effort conversion.
                text = extract_doc_text_via_soffice(p, workspace=self._workspace)
            else:
                return f"Error: unsupported extension: {suf}"
        except Exception as e:
            msg = str(e)
            if msg.startswith("no_converter:"):
                return (
                    "Error: 无法解析 .doc（当前环境缺少 LibreOffice/soffice）。"
                    "请将 .doc 另存为 .docx 后重试，或安装 LibreOffice 并确保 soffice 在 PATH 中。"
                )
            return f"Error: extract failed: {type(e).__name__}: {e}"

        if not text:
            return "Error: empty extracted text"
        if len(text) > max_chars:
            return text[: max_chars - 30] + "\n…(truncated)"
        return text

