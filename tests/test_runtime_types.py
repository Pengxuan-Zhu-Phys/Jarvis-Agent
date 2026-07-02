import asyncio
import dataclasses
import unittest
from collections.abc import AsyncIterator, Sequence

from jarvis_agent.runtime import (
    BackendFailure,
    CancelToken,
    ChatBackend,
    ChatEvent,
    ChatMessage,
    RetryPolicy,
    StreamEnd,
    TextDelta,
    ToolSpec,
    Usage,
    UsageReport,
)


class RuntimeTypesTests(unittest.TestCase):
    def test_messages_and_usage_are_frozen_slots(self) -> None:
        message = ChatMessage(role="user", content="hello")
        usage = Usage(prompt_tokens=3, completion_tokens=5, cached_tokens=1)

        self.assertFalse(hasattr(message, "__dict__"))
        self.assertEqual(usage.total_tokens, 8)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            message.content = "changed"  # type: ignore[misc]

    def test_cancel_token_raises_cancelled_error(self) -> None:
        token = CancelToken()
        self.assertFalse(token.cancelled)

        token.cancel()

        self.assertTrue(token.cancelled)
        with self.assertRaises(asyncio.CancelledError):
            token.raise_if_cancelled()

    def test_retry_policy_only_retries_recoverable_failures(self) -> None:
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=0.75)
        recoverable = BackendFailure(kind="connection", message="reset", recoverable=True)
        permanent = BackendFailure(kind="schema", message="bad response", recoverable=False)

        self.assertTrue(policy.should_retry(recoverable, attempt=1))
        self.assertTrue(policy.should_retry(recoverable, attempt=2))
        self.assertFalse(policy.should_retry(recoverable, attempt=3))
        self.assertFalse(policy.should_retry(permanent, attempt=1))
        self.assertEqual(policy.delay_for_attempt(1), 0.0)
        self.assertEqual(policy.delay_for_attempt(2), 0.5)
        self.assertEqual(policy.delay_for_attempt(3), 0.75)

        token = CancelToken()
        token.cancel()
        self.assertFalse(policy.should_retry(recoverable, attempt=1, cancel=token))

    def test_chat_backend_protocol_streams_events(self) -> None:
        class FakeBackend:
            def id(self) -> str:
                return "fake:test"

            def context_window(self) -> int:
                return 8192

            async def chat(
                self,
                messages: Sequence[ChatMessage],
                tools: Sequence[ToolSpec] = (),
                *,
                cancel: CancelToken,
            ) -> AsyncIterator[ChatEvent]:
                self.seen_messages = tuple(messages)
                yield TextDelta("hi")
                yield UsageReport(Usage(prompt_tokens=1, completion_tokens=1))
                yield StreamEnd("stop")

        async def run_test() -> None:
            backend = FakeBackend()
            self.assertIsInstance(backend, ChatBackend)
            events = [
                event
                async for event in backend.chat(
                    [ChatMessage(role="user", content="hello")],
                    cancel=CancelToken(),
                )
            ]
            self.assertEqual(backend.id(), "fake:test")
            self.assertEqual(backend.context_window(), 8192)
            self.assertEqual(events, [TextDelta("hi"), UsageReport(Usage(1, 1)), StreamEnd("stop")])

        asyncio.run(run_test())
