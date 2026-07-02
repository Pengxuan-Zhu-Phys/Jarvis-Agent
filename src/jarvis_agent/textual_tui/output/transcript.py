from __future__ import annotations

from textual.containers import VerticalScroll

from jarvis_agent.protocol.events import (
    AgentEvent,
    AssistantTextDelta,
    AssistantTextEnd,
    Error,
    LogLine,
    Metrics,
    Status,
    Summary,
    ToolCallStarted,
    ToolResult,
    UserPrompt,
    validate_event,
)

from .widgets import (
    AssistantBlock,
    ErrorBlock,
    LiveLogBlock,
    MetricsBlock,
    StatusBlock,
    SummaryBlock,
    ToolCallBlock,
    ToolResultBlock,
    UserBlock,
)


class TranscriptView(VerticalScroll):
    """Block-based transcript consumer for agent events."""

    can_focus = True

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.active_assistant: AssistantBlock | None = None
        self.active_live_log: LiveLogBlock | None = None
        self.auto_follow_output = True
        self._follow_refresh_pending = False

    def clear(self) -> None:
        self.active_assistant = None
        self.active_live_log = None
        self.auto_follow_output = True
        self._follow_refresh_pending = False
        self.remove_children()

    def consume(self, event: AgentEvent) -> None:
        validate_event(event)
        should_follow = self.auto_follow_output or self.is_at_vertical_end()
        if isinstance(event, UserPrompt):
            self.active_assistant = None
            self.active_live_log = None
            self.mount(UserBlock(event.text, event.timestamp))
        elif isinstance(event, AssistantTextDelta):
            if self.active_assistant is None:
                self.active_assistant = AssistantBlock()
                self.mount(self.active_assistant)
            self.active_assistant.append_delta(event.text)
        elif isinstance(event, AssistantTextEnd):
            if self.active_assistant is not None:
                self.active_assistant.finalize()
                self.active_assistant = None
        elif isinstance(event, ToolCallStarted):
            self.mount(ToolCallBlock(event.name, event.args))
        elif isinstance(event, ToolResult):
            self.mount(ToolResultBlock(event.name, event.output, event.ok))
            self._finalize_live_log()
        elif isinstance(event, LogLine):
            if self.active_live_log is None:
                self.active_live_log = LiveLogBlock()
                self.mount(self.active_live_log)
            self.active_live_log.append_line(event.text)
        elif isinstance(event, Status):
            self.mount(StatusBlock(event.message))
        elif isinstance(event, Error):
            self.mount(ErrorBlock(event.message))
        elif isinstance(event, Metrics):
            self.mount(MetricsBlock(event.summary, event.detail))
        elif isinstance(event, Summary):
            self.mount(SummaryBlock(event.title, event.body))
        if should_follow:
            self.follow_output()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if self._follow_refresh_pending and self.auto_follow_output:
            return
        self.auto_follow_output = self.is_at_vertical_end(new_value)

    def is_at_vertical_end(self, scroll_y: float | None = None) -> bool:
        value = self.scroll_y if scroll_y is None else scroll_y
        return value >= max(0, self.max_scroll_y - 1)

    def _scroll_to_end_if_following(self) -> None:
        if self.auto_follow_output:
            self.scroll_end(animate=False, immediate=True, force=True)
        self._follow_refresh_pending = False

    def follow_output(self) -> None:
        self.auto_follow_output = True
        self._follow_refresh_pending = True
        self.scroll_end(animate=False, immediate=True, force=True)
        self.call_after_refresh(self._scroll_to_end_if_following)

    def _user_scrolled_away_from_end(self) -> None:
        self._follow_refresh_pending = False
        self.auto_follow_output = False

    def _sync_auto_follow_after_user_scroll(self) -> None:
        self._follow_refresh_pending = False
        self.auto_follow_output = self.is_at_vertical_end()

    def _on_mouse_scroll_up(self, event) -> None:
        self._user_scrolled_away_from_end()
        super()._on_mouse_scroll_up(event)

    def _on_mouse_scroll_down(self, event) -> None:
        super()._on_mouse_scroll_down(event)
        self.call_after_refresh(self._sync_auto_follow_after_user_scroll)

    def action_scroll_up(self) -> None:
        self._user_scrolled_away_from_end()
        super().action_scroll_up()

    def action_scroll_home(self) -> None:
        self._user_scrolled_away_from_end()
        super().action_scroll_home()

    def action_scroll_down(self) -> None:
        super().action_scroll_down()
        self.call_after_refresh(self._sync_auto_follow_after_user_scroll)

    def action_scroll_end(self) -> None:
        super().action_scroll_end()
        self.auto_follow_output = True
        self.call_after_refresh(self._sync_auto_follow_after_user_scroll)

    def _finalize_live_log(self) -> None:
        if self.active_live_log is not None:
            self.active_live_log.flush()
            self.active_live_log = None
