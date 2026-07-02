from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Literal

from rich.markdown import Markdown
from rich.syntax import Syntax


SegmentKind = Literal["prose", "code"]
_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+.-]*)[^\n]*\n(?P<body>.*?)(?:\n```|\\Z)", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Segment:
    """Parsed assistant output segment."""

    kind: SegmentKind
    text: str
    language: str = ""


@lru_cache(maxsize=256)
def split_segments(text: str) -> tuple[Segment, ...]:
    """Split prose and fenced code blocks from assistant text."""

    segments: list[Segment] = []
    cursor = 0
    for match in _FENCE_RE.finditer(text):
        if match.start() > cursor:
            prose = text[cursor : match.start()]
            if prose:
                segments.append(Segment("prose", prose))
        language = (match.group("lang") or "text").strip() or "text"
        segments.append(Segment("code", match.group("body"), language))
        cursor = match.end()
    if cursor < len(text):
        tail = text[cursor:]
        if tail:
            segments.append(Segment("prose", tail))
    return tuple(segments) if segments else (Segment("prose", ""),)


def render_segment(segment: Segment):
    """Return the Rich renderable for a parsed output segment."""

    if segment.kind == "code":
        return Syntax(segment.text, segment.language or "text", word_wrap=True, background_color="default")
    return Markdown(segment.text)
