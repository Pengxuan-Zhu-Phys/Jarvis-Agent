from __future__ import annotations

import asyncio
import weakref
from collections.abc import Callable

from .events import AgentEvent, validate_event


EventConsumer = Callable[[AgentEvent], object]


class EventBus:
    """Small asyncio event bus for decoupling event producers and consumers."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._subscribers: set[weakref.ReferenceType[EventConsumer]] = set()

    def subscribe(self, consumer: EventConsumer) -> None:
        try:
            reference: weakref.ReferenceType[EventConsumer] = weakref.WeakMethod(consumer)  # type: ignore[arg-type]
        except TypeError:
            reference = weakref.ref(consumer)
        self._subscribers.add(reference)

    def unsubscribe(self, consumer: EventConsumer) -> None:
        self._subscribers = {reference for reference in self._subscribers if reference() != consumer}

    async def publish(self, event: AgentEvent) -> None:
        validate_event(event)
        await self._queue.put(event)
        self.drain_nowait()

    def drain_nowait(self) -> None:
        while True:
            try:
                event = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._dispatch(event)
            self._queue.task_done()

    def _dispatch(self, event: AgentEvent) -> None:
        live_references: set[weakref.ReferenceType[EventConsumer]] = set()
        for reference in self._subscribers:
            consumer = reference()
            if consumer is None:
                continue
            live_references.add(reference)
            consumer(event)
        self._subscribers = live_references
