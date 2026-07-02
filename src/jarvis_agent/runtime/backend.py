from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .types import BackendFailure, ChatEvent, ChatMessage, ToolSpec


class CancelToken:
    """Cooperative cancellation token shared by UI, agent loop, and backends."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError()


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0

    def should_retry(self, failure: BackendFailure, attempt: int, *, cancel: CancelToken | None = None) -> bool:
        if cancel is not None and cancel.cancelled:
            return False
        return failure.recoverable and attempt < self.max_attempts

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt <= 1:
            return 0.0
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 2)))


@runtime_checkable
class ChatBackend(Protocol):
    def id(self) -> str:
        """Stable runtime id used in traces and diagnostics."""

    def context_window(self) -> int:
        """Maximum context window in tokens."""

    def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        *,
        cancel: CancelToken,
    ) -> AsyncIterator[ChatEvent]:
        """Stream chat events until a terminal event or cancellation."""
