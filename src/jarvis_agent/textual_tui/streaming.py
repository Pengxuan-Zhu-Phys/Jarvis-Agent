from __future__ import annotations

import time


class StreamController:
    """Coalesce high-frequency stream deltas before repainting the active block."""

    def __init__(self, flush_interval: float = 0.05, max_buffer_chars: int = 80) -> None:
        self.flush_interval = flush_interval
        self.max_buffer_chars = max_buffer_chars
        self._buffer: list[str] = []
        self._last_flush = time.monotonic()

    def append(self, text: str) -> None:
        if text:
            self._buffer.append(text)

    def should_flush(self, now: float | None = None) -> bool:
        if not self._buffer:
            return False
        current = time.monotonic() if now is None else now
        return current - self._last_flush >= self.flush_interval or sum(len(part) for part in self._buffer) >= self.max_buffer_chars

    def flush(self, now: float | None = None) -> str:
        if not self._buffer:
            return ""
        current = time.monotonic() if now is None else now
        text = "".join(self._buffer)
        self._buffer.clear()
        self._last_flush = current
        return text

    def reset(self) -> None:
        self._buffer.clear()
        self._last_flush = time.monotonic()
