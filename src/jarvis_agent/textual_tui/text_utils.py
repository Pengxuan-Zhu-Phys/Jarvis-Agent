from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import time

from rich.cells import cell_len

def _escape_markup(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _home_relative_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        return str(resolved)
    return "~" if not relative.parts else f"~/{relative}"


def _format_token_count(tokens: int) -> str:
    if tokens >= 1_000:
        value = tokens / 1_000
        if value < 100:
            label = f"{value:.1f}".rstrip("0").rstrip(".")
            return f"{label}K"
        return f"{round(value):.0f}K"
    return str(tokens)


def _single_line(text: str, max_chars: int) -> str:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars - 1]}…"


def wrap_plain_text(text: str, width: int) -> list[str]:
    width = max(1, width)
    lines: list[str] = []
    for source_line in text.splitlines() or [""]:
        current = ""
        for character in source_line:
            character_width = max(1, cell_len(character))
            if current and cell_len(current) + character_width > width:
                lines.append(current)
                current = ""
            current += character
        lines.append(current)
    return lines or [""]


def pacman_ghost_frame(frame: int, max_spaces: int = 15) -> str:
    offset = ping_pong_offset(frame, max_spaces)
    return f"{' ' * offset}👻 👻 👻"


def ping_pong_offset(frame: int, max_value: int) -> int:
    if max_value <= 0:
        return 0
    period = max_value * 2
    position = frame % period
    return position if position <= max_value else period - position


def slash_suggestion_context(value: str, cursor_position: int) -> tuple[int, int, str] | None:
    cursor = max(0, min(cursor_position, len(value)))
    before_cursor = value[:cursor]
    start = before_cursor.rfind("/")
    if start < 0:
        return None
    token_prefix = before_cursor[start:cursor]
    if not token_prefix.startswith("/") or any(character.isspace() for character in token_prefix):
        return None
    end = cursor
    while end < len(value) and not value[end].isspace():
        end += 1
    return start, end, token_prefix


def location_to_text_index(text: str, location: tuple[int, int]) -> int:
    row, column = location
    if row <= 0:
        return max(0, min(column, len(text.split("\n", 1)[0])))
    lines = text.split("\n")
    row = max(0, min(row, len(lines) - 1))
    index = sum(len(line) + 1 for line in lines[:row])
    return min(len(text), index + max(0, min(column, len(lines[row]))))


def text_index_to_location(text: str, index: int) -> tuple[int, int]:
    index = max(0, min(index, len(text)))
    row = 0
    line_start = 0
    while True:
        newline = text.find("\n", line_start)
        if newline < 0 or newline >= index:
            return row, index - line_start
        row += 1
        line_start = newline + 1


METRICS_RE = re.compile(r"\n*\[metrics\]\s*(?P<metrics>.*)\s*$", re.DOTALL)


def split_output_metrics(output: str) -> tuple[str, str]:
    body, metrics, _ = split_output_metrics_detail(output)
    return body, metrics


def split_output_metrics_detail(output: str) -> tuple[str, str, str]:
    stripped = output.rstrip()
    match = METRICS_RE.search(stripped)
    if not match:
        return output, "", ""
    body = stripped[: match.start()].rstrip()
    metrics_detail = " ".join(match.group("metrics").split())
    return body, compact_metrics(metrics_detail), metrics_detail


def compact_metrics(metrics: str) -> str:
    def match_value(pattern: str) -> str:
        match = re.search(pattern, metrics)
        return match.group(1) if match else ""

    prompt = match_value(r"prompt:\s*(\d+)\s*tokens")
    generation = match_value(r"generation:\s*(\d+)\s*tokens")
    context = match_value(r"context:\s*(\d+)\s*tokens")
    memory = match_value(r"peak memory:\s*([0-9.]+)\s*GB")
    parts: list[str] = []
    if prompt:
        parts.append(f"prompt {prompt} tok")
    if generation:
        parts.append(f"gen {generation} tok")
    if context:
        parts.append(f"ctx {context} tok")
    if memory:
        parts.append(f"mem {memory} GB")
    return " · ".join(parts) if parts else metrics


def parse_context_metric_tokens(metrics: str) -> int | None:
    match = re.search(r"context:\s*(\d+)\s*tokens", metrics)
    return int(match.group(1)) if match else None


def _relative_time_label(created_at: float) -> str:
    elapsed = max(0, int(time.time() - created_at))
    if elapsed < 60:
        return "now"
    minutes = elapsed // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr"
    return f"{hours // 24} d"


def _exact_time_label(created_at: float) -> str:
    return datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S")


def estimate_context_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, round(len(stripped) / 4))


def wrap_output_text(text: str, width: int) -> tuple[str, int]:
    pieces: list[str] = []
    column = 0
    for character in text:
        if character == "\r":
            continue
        if character == "\n":
            pieces.append(character)
            column = 0
            continue
        character_width = max(1, cell_len(character))
        if column and column + character_width > width:
            pieces.append("\n")
            column = 0
        pieces.append(character)
        column += character_width
    return "".join(pieces), column


def current_time_label() -> str:
    return datetime.now().strftime("%-I:%M %p")


def _compact_path(path: str, max_chars: int = 56) -> str:
    if len(path) <= max_chars:
        return path
    return f"...{path[-max_chars + 3:]}"


def _compact_middle_path(path: str, max_chars: int = 56) -> str:
    if len(path) <= max_chars:
        return path
    if max_chars <= 6:
        return path[: max(0, max_chars - 3)] + "..."
    head = max(3, int(max_chars * 0.65))
    tail = max_chars - head - 3
    if tail <= 0:
        return f"{path[: max_chars - 3]}..."
    return f"{path[:head]}...{path[-tail:]}"
