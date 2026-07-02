import unittest
import asyncio
from dataclasses import FrozenInstanceError

from jarvis_agent.protocol import EventBus
from jarvis_agent.protocol.events import PROTOCOL_VERSION, UserPrompt, validate_event


class ProtocolEventTests(unittest.TestCase):
    def test_user_prompt_is_frozen_and_slotted(self) -> None:
        event = UserPrompt(text="hello", timestamp="now")

        with self.assertRaises(FrozenInstanceError):
            event.text = "changed"  # type: ignore[misc]
        with self.assertRaises((AttributeError, TypeError)):
            event.extra = "nope"  # type: ignore[attr-defined]

    def test_validate_event_accepts_v1_metadata(self) -> None:
        validate_event(UserPrompt(text="hello", timestamp="now", metadata={"protocol_version": PROTOCOL_VERSION}))

    def test_validate_event_rejects_future_protocol_version(self) -> None:
        event = UserPrompt(text="hello", timestamp="now", metadata={"protocol_version": PROTOCOL_VERSION + 1})

        with self.assertRaises(ValueError):
            validate_event(event)

    def test_event_bus_publishes_to_subscribers(self) -> None:
        seen = []
        bus = EventBus()

        class Consumer:
            def consume(self, event) -> None:
                seen.append(event)

        consumer = Consumer()
        bus.subscribe(consumer.consume)

        asyncio.run(bus.publish(UserPrompt(text="hello", timestamp="now")))

        self.assertEqual(seen, [UserPrompt(text="hello", timestamp="now")])
