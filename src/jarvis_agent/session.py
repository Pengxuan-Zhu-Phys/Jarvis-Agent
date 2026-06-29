from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


JARVIS_HOME = Path.home() / ".jarvis"
SESSIONS_FILE = JARVIS_HOME / "sessions.jsonl"


@dataclass(frozen=True)
class SessionEvent:
    session_id: str
    timestamp: str
    kind: str
    text: str


class SessionStore:
    def __init__(self, path: Path = SESSIONS_FILE) -> None:
        self.path = path

    def new_session_id(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def append(self, session_id: str, kind: str, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "text": text,
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_events(self) -> list[SessionEvent]:
        if not self.path.exists():
            return []
        events: list[SessionEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(
                SessionEvent(
                    session_id=str(record.get("session_id", "")),
                    timestamp=str(record.get("timestamp", "")),
                    kind=str(record.get("kind", "")),
                    text=str(record.get("text", "")),
                )
            )
        return events

    def recent_session_ids(self, limit: int = 6) -> list[str]:
        seen: list[str] = []
        for event in reversed(self.load_events()):
            if event.session_id and event.session_id not in seen:
                seen.append(event.session_id)
            if len(seen) >= limit:
                break
        return seen

    def events_for(self, session_id: str) -> list[SessionEvent]:
        return [event for event in self.load_events() if event.session_id == session_id]

    def latest_session_id(self) -> str | None:
        ids = self.recent_session_ids(limit=1)
        return ids[0] if ids else None

    def format_recent(self, limit: int = 6) -> str:
        ids = self.recent_session_ids(limit=limit)
        if not ids:
            return f"No saved sessions yet. History will be written to {self.path}."
        lines = [f"Saved sessions in {self.path}:"]
        for index, session_id in enumerate(ids, start=1):
            events = self.events_for(session_id)
            first_user = next((event.text for event in events if event.kind == "user"), "")
            preview = _single_line(first_user, max_chars=72) if first_user else "(no user prompt recorded)"
            lines.append(f"  {index}. {session_id}  {preview}")
        lines.append("")
        lines.append("Use /resume latest or /resume SESSION_ID to show a transcript.")
        return "\n".join(lines)

    def format_transcript(self, session_id: str | None = None) -> str:
        resolved = session_id or self.latest_session_id()
        if not resolved:
            return self.format_recent()
        if resolved == "latest":
            resolved = self.latest_session_id()
        if not resolved:
            return self.format_recent()
        events = self.events_for(resolved)
        if not events:
            return f"No session found for {resolved}."
        lines = [f"Session {resolved}"]
        for event in events:
            if event.kind == "session_start":
                continue
            label = event.kind.replace("_", " ")
            lines.append(f"\n[{event.timestamp}] {label}")
            lines.append(event.text)
        return "\n".join(lines).strip()


def _single_line(text: str, max_chars: int) -> str:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars - 1]}…"
