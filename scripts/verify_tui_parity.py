from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from jarvis_agent.protocol import AssistantTextDelta, AssistantTextEnd, LogLine, Summary, ToolResult, UserPrompt
from jarvis_agent.textual_tui.output.transcript import TranscriptView
from jarvis_agent.textual_tui.output.widgets import AssistantBlock, LiveLogBlock, SummaryBlock, ToolResultBlock, UserBlock


class TranscriptHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield TranscriptView(id="log")


async def main() -> None:
    async with TranscriptHarness().run_test() as pilot:
        transcript = pilot.app.query_one("#log", TranscriptView)
        transcript.consume(UserPrompt(text="show markdown", timestamp="now"))
        transcript.consume(AssistantTextDelta(text="# Heading\n\n```python\nprint('ok')\n```"))
        transcript.consume(AssistantTextEnd())
        transcript.consume(LogLine(text="line 1"))
        transcript.consume(LogLine(text="line 2"))
        transcript.consume(ToolResult(name="shell", output="complete"))
        transcript.consume(Summary(title="Index", body="scanned files: 1"))
        await pilot.pause()

        assert len(transcript.query(UserBlock).nodes) == 1
        assert len(transcript.query(AssistantBlock).nodes) == 1
        assert len(transcript.query(LiveLogBlock).nodes) == 1
        assert len(transcript.query(ToolResultBlock).nodes) == 1
        assert len(transcript.query(SummaryBlock).nodes) == 1


if __name__ == "__main__":
    asyncio.run(main())
