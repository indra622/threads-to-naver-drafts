from __future__ import annotations

import json
import os
import select
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from .models import ThreadPost

MCP_PROTOCOL_VERSION = "2025-11-25"


@dataclass(frozen=True)
class SimplenoteNote:
    id: str
    content: str
    tags: tuple[str, ...]
    created: datetime
    modified: datetime | None = None

    def to_draft_item(self) -> ThreadPost:
        title, body = split_note_content(self.content)
        return ThreadPost(
            id=f"simplenote:{self.id}",
            text=body,
            timestamp=self.created,
            permalink=f"simplenote://note/{self.id}",
            media_type="TEXT_POST",
            title_override=title,
            source_name="Simplenote",
        )


def split_note_content(content: str) -> tuple[str, str]:
    """Use Simplenote's first line as the title and preserve the remaining body."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    title, separator, body = normalized.partition("\n")
    return title.strip()[:100], body if separator else ""


class SimplenoteMCPClient:
    """Small stdio client for Automattic's official read-only MCP server."""

    def __init__(
        self,
        command: Path,
        store_path: Path | None,
        *,
        timeout_seconds: float = 30,
    ) -> None:
        self.command = command
        self.store_path = store_path
        self.timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._request_id = 0

    def list_tagged_notes(self, tag: str, limit: int = 100) -> list[SimplenoteNote]:
        if not 1 <= limit <= 100:
            raise ValueError("Simplenote MCP list limit must be between 1 and 100.")
        self._start()
        listed = self._call_tool(
            "list_notes",
            {"tag": tag, "limit": limit, "include_deleted": False},
        ).get("notes")
        if not isinstance(listed, list):
            raise TypeError("Simplenote MCP returned an invalid note list.")

        notes: list[SimplenoteNote] = []
        for item in listed:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise TypeError("Simplenote MCP returned an invalid note summary.")
            payload = self._call_tool(
                "get_note",
                {"id": item["id"], "include_deleted": False},
            ).get("note")
            notes.append(_decode_note(payload, required_tag=tag))
        return notes

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _start(self) -> None:
        if self._process is not None:
            return
        if not self.command.is_file():
            raise FileNotFoundError(
                f"Missing Simplenote MCP executable: {self.command}. Run npm install."
            )
        if self.store_path is not None and not self.store_path.is_file():
            raise FileNotFoundError(
                f"Missing Simplenote local store: {self.store_path}. "
                "Install and sync the Simplenote macOS app first."
            )
        env = os.environ.copy()
        env["SIMPLENOTE_MCP_DISABLE_TELEMETRY"] = "1"
        command = [str(self.command)]
        if self.store_path is not None:
            command.extend(["--path", str(self.store_path)])
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "threads-to-naver-drafts",
                    "version": "0.2.0",
                },
            },
        )
        self._notify("notifications/initialized", {})

    def _call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        response = self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        if response.get("isError") is True:
            raise RuntimeError(f"Simplenote MCP tool failed: {name}")
        structured = response.get("structuredContent")
        if not isinstance(structured, dict):
            raise TypeError(f"Simplenote MCP tool returned no structured data: {name}")
        return structured

    def _request(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            message = self._read_message()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"Simplenote MCP error: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise TypeError("Simplenote MCP returned an invalid response.")
            return result

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: dict[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("Simplenote MCP process is not running.")
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise RuntimeError("Simplenote MCP process is not running.")
        ready, _, _ = select.select(
            [process.stdout], [], [], self.timeout_seconds
        )
        if not ready:
            raise RuntimeError("Timed out waiting for Simplenote MCP.")
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read().strip() if process.stderr else ""
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(f"Simplenote MCP exited unexpectedly{detail}")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError("Simplenote MCP returned invalid JSON.") from error
        if not isinstance(message, dict):
            raise TypeError("Simplenote MCP returned an invalid message.")
        return message


def _decode_note(payload: object, *, required_tag: str) -> SimplenoteNote:
    if not isinstance(payload, dict):
        raise TypeError("Simplenote MCP returned an invalid note.")
    note_id = payload.get("id")
    content = payload.get("content")
    tags = payload.get("tags")
    if not isinstance(note_id, str) or not isinstance(content, str):
        raise TypeError("Simplenote MCP returned an invalid note.")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise TypeError("Simplenote MCP returned invalid note tags.")
    if required_tag not in tags or payload.get("deleted") is True:
        raise ValueError("Simplenote MCP returned an untagged or deleted note.")
    modified_value = payload.get("modified")
    modified = _parse_timestamp(modified_value) if modified_value else None
    created_value = payload.get("created") or modified_value
    created = _parse_timestamp(created_value)
    return SimplenoteNote(
        id=note_id,
        content=content,
        tags=tuple(tags),
        created=created,
        modified=modified,
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("Simplenote note has no valid creation timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError("Simplenote note has an invalid timestamp.") from error
    if parsed.tzinfo is None:
        raise RuntimeError("Simplenote timestamp must include a timezone.")
    return parsed
