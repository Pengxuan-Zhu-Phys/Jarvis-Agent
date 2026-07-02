from __future__ import annotations

import time

from rich.console import Group
from textual.widgets import RichLog, Static

from .blocks import Segment, render_segment, split_segments


class TranscriptBlock(Static):
    """Base static block used by the transcript."""

    DEFAULT_CSS = """
    TranscriptBlock {
        height: auto;
        margin-bottom: 1;
    }
    """

    def __init__(self, renderable="", *, block_type: str, **kwargs) -> None:
        super().__init__(renderable, classes=f"transcript-block {block_type}", **kwargs)


class UserBlock(TranscriptBlock):
    def __init__(self, text: str, timestamp: str) -> None:
        super().__init__(f"[#8d93a1]{timestamp}[/]\n[#f5f7fb bold]User[/]\n{text}", block_type="user-block")


class AssistantBlock(TranscriptBlock):
    def __init__(self) -> None:
        super().__init__("[#aee4fc bold]Assistant[/]\n", block_type="assistant-block")
        self._raw_parts: list[str] = []
        self._segments: tuple[Segment, ...] | None = None

    @property
    def raw_text(self) -> str:
        return "".join(self._raw_parts)

    def append_delta(self, text: str) -> None:
        self._raw_parts.append(text)
        self.update(f"[#aee4fc bold]Assistant[/]\n{self.raw_text}")

    def finalize(self) -> None:
        text = self.raw_text
        self._segments = split_segments(text)
        self._raw_parts.clear()
        self.update(Group("[#aee4fc bold]Assistant[/]", *(render_segment(segment) for segment in self._segments)))


class ToolCallBlock(TranscriptBlock):
    def __init__(self, name: str, args: object) -> None:
        suffix = f" {args}" if args else ""
        super().__init__(f"[#ffe45c bold]Tool[/] {name}{suffix}", block_type="tool-call-block")


class ToolResultBlock(TranscriptBlock):
    def __init__(self, name: str, output: str, ok: bool = True) -> None:
        status = "ok" if ok else "failed"
        super().__init__(f"[#ffe45c bold]{name}[/] [#8d93a1]{status}[/]\n{output}", block_type="tool-result-block")


class SummaryBlock(TranscriptBlock):
    def __init__(self, title: str, body: str) -> None:
        super().__init__(f"[#b897ff bold]{title}[/]\n{body}", block_type="summary-block")


class ErrorBlock(TranscriptBlock):
    def __init__(self, message: str) -> None:
        super().__init__(f"[#ff6b6b bold]Error[/]\n{message}", block_type="error-block")


class StatusBlock(TranscriptBlock):
    def __init__(self, message: str) -> None:
        super().__init__(f"[#8d93a1]{message}[/]", block_type="status-block")


class MetricsBlock(TranscriptBlock):
    def __init__(self, summary: str, detail: str = "") -> None:
        text = summary if not detail else f"{summary}\n[#6f7785]{detail}[/]"
        super().__init__(text, block_type="metrics-block")


class LiveLogBlock(RichLog):
    """RichLog block for long-running tool output."""

    DEFAULT_CSS = """
    LiveLogBlock {
        height: auto;
        max-height: 16;
        margin-bottom: 1;
        border: round #303745;
        scrollbar-size-horizontal: 0;
    }
    """

    def __init__(self) -> None:
        super().__init__(highlight=False, markup=False, wrap=True, classes="transcript-block live-log-block")
        self._pending_lines: list[str] = []
        self._last_flush = time.monotonic()

    def append_line(self, text: str, *, force: bool = False) -> None:
        self._pending_lines.append(text)
        now = time.monotonic()
        if force or len(self._pending_lines) >= 20 or now - self._last_flush >= 0.05:
            self.flush()

    def flush(self) -> None:
        if not self._pending_lines:
            return
        for line in self._pending_lines:
            self.write(line)
        self._pending_lines.clear()
        self._last_flush = time.monotonic()
