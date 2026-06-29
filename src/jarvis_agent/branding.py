from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


FALLBACK_LOGO_PATTERN = (
    "BBBW....",
    "BBWWY...",
    "BWWWY...",
    "BBWWYY..",
    "BBBWY...",
    "WWWWYYYY",
    "BBWWYY..",
    "BBBWY...",
)

FALLBACK_BANNER_LINES = (
    "JARVIS",
    "Just a Robust and Versatile Interface Suite for HEP",
    "Author: Pengxuan Zhu, Erdong Guo.",
)

TEXT_GRADIENT_COLORS = (
    "#2f7fd8",
    "#73b8f4",
    "#aee4fc",
    "#b8ffe4",
    "#d5f884",
    "#f8f675",
    "#ffe95d",
    "#ffdc3f",
)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LOGO_DOT_PREFIX = "⬤ " * 8


@dataclass(frozen=True)
class JarvisBranding:
    logo_pattern: tuple[str, ...]
    banner_lines: tuple[str, ...]
    version_lines: tuple[str, ...]
    source: str

    def plain_logo(self) -> str:
        palette = {"B": "B", "W": "W", "Y": "Y", ".": "."}
        return "\n".join(" ".join(palette.get(char, char) for char in row) for row in self.logo_pattern)

    def logo_widths(self, side: str) -> tuple[int, ...]:
        if side == "left":
            return tuple(row[:4].count("W") for row in self.logo_pattern)
        if side == "right":
            return tuple(row[4:8].count("Y") for row in self.logo_pattern)
        raise ValueError(f"Unknown logo side: {side}")

    def compact_version_lines(self) -> tuple[str, ...]:
        return _drop_resource_lines(self.version_lines)


def load_jarvis_branding(project_root: Path, command: str = "Jarvis") -> JarvisBranding:
    logo_text = _read_logo_file(project_root)
    logo_pattern, banner_lines = _parse_logo_file(logo_text)
    version_output = _run_jarvis_version(command)
    version_lines = _clean_version_lines(version_output)

    source = "Jarvis -v"
    if not version_lines:
        source = "jarvishep/card/logo" if logo_text else "fallback"
        version_lines = tuple(banner_lines)

    return JarvisBranding(
        logo_pattern=logo_pattern or FALLBACK_LOGO_PATTERN,
        banner_lines=banner_lines or FALLBACK_BANNER_LINES,
        version_lines=version_lines,
        source=source,
    )


def _read_logo_file(project_root: Path) -> str:
    candidates = [
        project_root / "jarvishep" / "card" / "logo",
        project_root.parent / "Jarvis-HEP" / "jarvishep" / "card" / "logo",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return ""


def _parse_logo_file(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    pattern: list[str] = []
    banner: list[str] = []
    for line in text.splitlines():
        prefix = line[:8]
        if len(prefix) == 8 and set(prefix) <= {"B", "W", "Y", "."}:
            pattern.append(prefix)
            rest = line[8:].strip()
            if rest:
                banner.append(rest)
    return tuple(pattern[:8]), tuple(banner)


def _run_jarvis_version(command: str) -> str:
    try:
        completed = subprocess.run(
            (command, "-v"),
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _clean_version_lines(text: str) -> tuple[str, ...]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = ANSI_RE.sub("", raw).rstrip()
        line = _strip_logo_dot_prefix(line)
        if not line.strip():
            continue
        lines.append(line)
    return tuple(lines)


def _drop_resource_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    kept: list[str] = []
    for line in lines:
        if line.strip() == "Resources:":
            break
        kept.append(line)
    return tuple(kept)


def _strip_logo_dot_prefix(line: str) -> str:
    if not line.startswith(LOGO_DOT_PREFIX):
        return line
    rest = line[len(LOGO_DOT_PREFIX) :]
    if rest.startswith("  "):
        return rest[2:]
    return rest
