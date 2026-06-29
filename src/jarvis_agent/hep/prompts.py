from __future__ import annotations

from pathlib import Path


def build_explain_file_prompt(path: Path, project_root: Path, max_chars: int = 16_000) -> str:
    resolved = path.expanduser().resolve()
    root = project_root.expanduser().resolve()
    text = resolved.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[TRUNCATED]"
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        relative = str(resolved)
    return f"""You are a local HEP software assistant.

Explain this file for a user who needs to correctly use and configure the package.

Required answer shape:
1. Purpose of the file.
2. Important functions/classes/settings.
3. How it connects to the surrounding package.
4. Configuration or YAML implications, if any.
5. Risks, assumptions, or things to verify.

File: {relative}

```text
{text}
```
"""

