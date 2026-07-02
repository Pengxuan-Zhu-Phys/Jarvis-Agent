from __future__ import annotations

from rich.cells import cell_len
from textual.widgets import TextArea


PROMPT_MAX_LINES = 5
COMMAND_CHOICES = (
    ("/home", "open the Jarvis-Agent home page"),
    ("/model", "choose or scan local MLX models"),
    ("/resume", "list saved sessions"),
    ("/status", "show project, model, and history status"),
    ("/index", "scan the configured HEP package"),
    ("/yaml", "review a YAML configuration file"),
    ("/explain", "build an explanation prompt for a source file"),
    ("/ask", "send a prompt to the local model"),
    ("/clear", "clear the session output"),
    ("/quit", "exit Jarvis-Agent"),
)
ARG_COMMANDS = {"/ask", "/explain", "/yaml"}


class PromptTextArea(TextArea):
    """TextArea that submits on Enter and inserts newlines on Shift+Enter."""

    async def _on_key(self, event) -> None:
        if event.key == "shift+enter":
            event.stop()
            event.prevent_default()
            self.insert("\n")
            if hasattr(self.app, "update_composer_height"):
                self.app.update_composer_height()
            return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if hasattr(self.app, "suggestion_values") and self.app.suggestion_values:
                await self.app.apply_highlighted_suggestion(submit=True)
            elif hasattr(self.app, "submit_prompt"):
                self.app.submit_prompt()
            return
        await super()._on_key(event)


def prompt_visual_line_count(text: str, width: int) -> int:
    """Return the visual line count after soft wrapping at width."""

    safe_width = max(1, width)
    lines = text.split("\n") if text else [""]
    return sum(max(1, (cell_len(line) + safe_width - 1) // safe_width) for line in lines)
