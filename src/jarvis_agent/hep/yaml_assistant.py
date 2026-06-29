from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class YAMLReview:
    path: Path
    ok: bool
    messages: tuple[str, ...]

    def format(self) -> str:
        status = "OK" if self.ok else "ISSUES"
        lines = [f"{status}: {self.path}"]
        lines.extend(f"- {message}" for message in self.messages)
        return "\n".join(lines)


def review_yaml_file(path: Path) -> YAMLReview:
    path = path.expanduser().resolve()
    text = path.read_text(encoding="utf-8", errors="replace")
    messages: list[str] = []

    parsed, parse_error = _try_parse_yaml(text)
    if parse_error:
        messages.append(parse_error)
    elif parsed is None:
        messages.extend(_fallback_yaml_checks(text))
    else:
        messages.append("YAML parsed successfully.")
        if isinstance(parsed, dict):
            messages.append(f"Top-level keys: {', '.join(map(str, parsed.keys())) or '[none]'}")
        else:
            messages.append(f"Top-level object type: {type(parsed).__name__}")

    if "\t" in text:
        messages.append("Tabs detected; YAML indentation should use spaces.")
    if "{{" in text or "}}" in text:
        messages.append("Template markers detected; verify rendering before package execution.")
    if any(line.rstrip() != line for line in text.splitlines()):
        messages.append("Trailing whitespace detected.")

    has_error = any(message.startswith("YAML parse error") for message in messages)
    return YAMLReview(path=path, ok=not has_error, messages=tuple(messages or ["No obvious issues found."]))


def _try_parse_yaml(text: str) -> tuple[object | None, str | None]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return None, None

    try:
        return yaml.safe_load(text), None
    except Exception as exc:  # pragma: no cover - depends on optional parser
        return None, f"YAML parse error: {exc}"


def _fallback_yaml_checks(text: str) -> list[str]:
    messages = ["PyYAML is not installed; using lightweight structural checks."]
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped and not stripped.startswith("-"):
            messages.append(f"Line {line_number}: no ':' or list marker found; verify YAML syntax.")
    return messages
