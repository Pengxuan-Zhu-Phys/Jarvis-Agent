import asyncio
import unittest

from jarvis_agent.protocol import AssistantTextDelta, AssistantTextEnd, Summary, UserPrompt
from jarvis_agent.textual_tui.output.transcript import TranscriptView
from jarvis_agent.textual_tui.output.widgets import AssistantBlock, SummaryBlock, UserBlock
from textual.app import App, ComposeResult


class TranscriptHarness(App[None]):
    CSS = "#log { height: 8; }"

    def compose(self) -> ComposeResult:
        yield TranscriptView(id="log")


class TranscriptViewTests(unittest.TestCase):
    def test_consume_builds_blocks_and_finalizes_assistant(self) -> None:
        async def run_test() -> None:
            async with TranscriptHarness().run_test() as pilot:
                transcript = pilot.app.query_one("#log", TranscriptView)
                transcript.consume(UserPrompt(text="hello", timestamp="now"))
                transcript.consume(AssistantTextDelta(text="Here\n```python\nprint('hi')\n```"))
                transcript.consume(AssistantTextEnd())
                transcript.consume(Summary(title="Index", body="done"))
                await pilot.pause()

                self.assertEqual(len(transcript.query(UserBlock).nodes), 1)
                assistant = transcript.query_one(AssistantBlock)
                self.assertEqual(assistant.raw_text, "")
                self.assertEqual(len(transcript.query(SummaryBlock).nodes), 1)

        asyncio.run(run_test())

    def test_auto_follow_pauses_when_user_scrolls_away_from_bottom(self) -> None:
        async def run_test() -> None:
            async with TranscriptHarness().run_test(size=(80, 12)) as pilot:
                transcript = pilot.app.query_one("#log", TranscriptView)
                for index in range(30):
                    transcript.consume(Summary(title=f"Block {index}", body="line\nline\nline"))
                await pilot.pause()

                self.assertGreater(transcript.max_scroll_y, 0)
                self.assertTrue(transcript.is_at_vertical_end())

                transcript.scroll_to(y=0, animate=False, immediate=True)
                await pilot.pause()
                self.assertFalse(transcript.auto_follow_output)
                pinned_scroll_y = transcript.scroll_y

                transcript.consume(Summary(title="New while reading", body="do not jump"))
                await pilot.pause()
                self.assertEqual(transcript.scroll_y, pinned_scroll_y)
                self.assertFalse(transcript.auto_follow_output)

                transcript.scroll_end(animate=False, immediate=True)
                await pilot.pause()
                self.assertTrue(transcript.auto_follow_output)

                transcript.consume(Summary(title="New at bottom", body="follow again"))
                await pilot.pause()
                self.assertTrue(transcript.is_at_vertical_end())

        asyncio.run(run_test())

    def test_auto_follow_survives_streaming_block_growth(self) -> None:
        async def run_test() -> None:
            async with TranscriptHarness().run_test(size=(80, 12)) as pilot:
                transcript = pilot.app.query_one("#log", TranscriptView)
                transcript.consume(UserPrompt(text="stream", timestamp="now"))
                for index in range(120):
                    transcript.consume(AssistantTextDelta(text=f"line {index}\n"))
                await pilot.pause()

                self.assertGreater(transcript.max_scroll_y, 0)
                self.assertTrue(transcript.auto_follow_output)
                self.assertTrue(transcript.is_at_vertical_end())
                self.assertEqual(transcript.vertical_scrollbar.position, transcript.scroll_y)

        asyncio.run(run_test())
