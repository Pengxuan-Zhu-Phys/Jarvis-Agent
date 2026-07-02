from __future__ import annotations

import threading
import time

from rich.cells import cell_len
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import ListItem, ListView, Static, TextArea


from jarvis_agent.branding import TEXT_GRADIENT_COLORS
from jarvis_agent.config import AgentConfig, compact_model_name, local_available_models, model_badge_name
from jarvis_agent.protocol import AssistantTextDelta, AssistantTextEnd, Error, Metrics, Summary, ToolCallStarted, ToolResult, UserPrompt
from jarvis_agent.tui import TUIResponse, TerminalUI

from .animation import LogoMonitorConfig, pacman_ghost_frame, render_logo_monitor_frame
from .composer import ARG_COMMANDS, COMMAND_CHOICES, PROMPT_MAX_LINES, PromptTextArea, prompt_visual_line_count
from .gitinfo import get_git_info
from .history import HistoryModel, TurnRecord, history_index_label, history_toggle_label, prompt_needs_expansion
from .output.transcript import TranscriptView
from .streaming import StreamController
from .text_utils import (
    _compact_middle_path,
    _escape_markup,
    _exact_time_label,
    _format_token_count,
    _home_relative_path,
    _relative_time_label,
    _single_line,
    current_time_label,
    estimate_context_tokens,
    location_to_text_index,
    parse_context_metric_tokens,
    slash_suggestion_context,
    split_output_metrics_detail,
    text_index_to_location,
    wrap_plain_text,
)


class JarvisAgentApp(App[None]):
    CONTEXT_LIMIT_TOKENS = 2048
    GHOST_TRACK_SPACES = 15
    GHOST_WIDTH = 28
    RUN_CONTROL_WIDTH = 28
    LOGO_MONITOR = LogoMonitorConfig()
    SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    ARC_SPINNER_FRAMES = ("◜", "◟", "◞", "◝")
    RESPONSE_STREAM_SECONDS_PER_CHAR = 0.012
    PROMPT_MAX_LINES = PROMPT_MAX_LINES
    COMMAND_CHOICES = COMMAND_CHOICES
    ARG_COMMANDS = ARG_COMMANDS

    CSS_PATH = "styles.tcss"


    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear"),
        ("ctrl+h", "toggle_history", "History"),
    ]

    def __init__(self, agent_config: AgentConfig) -> None:
        super().__init__()
        self.agent_config = agent_config
        self.ui = TerminalUI(agent_config)
        self.splash_frame = 0
        self.home_visible = True
        self.thinking_started_at: float | None = None
        self.thinking_prompt = ""
        self.thinking_context_tokens = 0
        self.measured_context_tokens: int | None = None
        self.responding_started_at: float | None = None
        self.response_text = ""
        self.response_index = 0
        self.response_should_continue = True
        self.response_last_tick = 0.0
        self.stream_controller = StreamController()
        self.output_raw_text = ""
        self.spinner_index = 0
        self.last_copied_selection = ""
        self.copy_notice_until = 0.0
        self.suggestion_mode: str | None = None
        self.suggestion_values: list[str] = []
        self.suggestion_start = 0
        self.suggestion_end = 0
        self.todo_panel_open = False
        self.todo_items: list[str] = []
        self.history_model = HistoryModel()
        self.turn_records: list[TurnRecord] = self.history_model.records
        self.current_turn_index: int | None = None
        self.history_mode = "turns"
        self.history_expanded = False
        self.history_pinned = False
        self.expanded_turn_prompts: set[int] = self.history_model.expanded_turn_prompts
        self.suppress_next_history_selection = False
        self.pending_history_digit = ""
        self.session_choices: list[str] = []
        self.output_metrics_text = ""
        self.output_metrics_detail = ""
        self.ghost_frame = 0
        self.notice_until = 0.0
        self.next_generation_id = 0
        self.active_generation_id: int | None = None
        self.cancelled_generation_ids: set[int] = set()
        self.generation_cancel_requested = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Static(self.render_git_status_info(), id="git-status-info"),
                Static(self.render_repo_path_info(), id="repo-path-info"),
                Static("", id="context-info"),
                Static(self.render_todo_info(), id="todo-info"),
                id="topbar",
            ),
            Static(self.render_todo_panel(), id="todo-panel"),
            ListView(id="turn-history"),
            Horizontal(
                Static(self.render_logo_monitor_frame(), id="logo-monitor"),
                Static(self.render_home_panel(), id="home-panel"),
                id="hero",
            ),
            TranscriptView(id="log"),
            id="workspace",
        )
        yield Static("", id="notice")
        yield Static("", id="thinking")
        yield Static("", id="output-metrics")
        yield Static("", id="pacman-ghosts")
        yield Horizontal(
            Static("", id="token-counter"),
            Static("\\[stop]", id="stop-button"),
            id="run-control",
        )
        yield ListView(id="suggestions")
        yield Vertical(
            Horizontal(
                Static("❱", id="prompt-icon"),
                PromptTextArea(
                    placeholder="Ask Jarvis-Agent, or use /help, /home, /model, /resume, /index ...",
                    id="prompt",
                    compact=True,
                    show_line_numbers=False,
                    soft_wrap=True,
                ),
                id="prompt-row",
            ),
            id="composer",
        )

    def on_mount(self) -> None:
        self.title = "Jarvis-Agent"
        self.sub_title = self.agent_config.project.name
        self.enforce_output_scrollbars()
        self.update_composer_caption()
        self.update_topbar_status()
        self.hide_todo_panel()
        self.set_chat_visible(False)
        self.query_one("#prompt", TextArea).focus()
        self.update_composer_height()
        self.hide_suggestions()
        self.set_interval(0.12, self.animate_home)
        self.set_interval(0.10, self.update_thinking_status)
        self.set_interval(0.03, self.update_response_stream)
        self.set_interval(0.20, self.auto_copy_selection)
        self.set_interval(0.20, self.update_context_info)
        self.set_interval(0.35, self.animate_pacman_ghosts)
        self.set_interval(1.0, self.update_ghost_clock)
        self.hide_thinking_status()
        self.clear_output_metrics_caption()
        self.animate_pacman_ghosts()
        self.update_ghost_clock()

    def process_raw(self, raw: str) -> None:
        if raw == "/home":
            self.show_home()
            return

        self.hide_home()
        self.set_chat_visible(True)

        if raw == "/clear":
            self.query_one("#log", TranscriptView).clear()
            self.clear_output_metrics_caption()
            self.reset_output_buffer()
            self.update_topbar_status()
            return

        self.start_new_turn(raw)

        if self.is_llm_request(raw):
            self.start_llm_request(raw)
            return

        try:
            response = self.ui.dispatch(raw)
        except Exception as exc:
            self.write_output(f"ERROR: {exc}")
            return

        self.sync_config_from_ui()
        if response.output:
            self.write_output(response.output)
        if not response.should_continue:
            self.exit()
        self.update_topbar_status()

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "prompt":
            return
        self.update_composer_height()
        await self.refresh_suggestions(event.text_area.text, self.prompt_cursor_index(event.text_area))

    def on_click(self, event) -> None:
        widget = getattr(event, "widget", None)
        widget_id = getattr(widget, "id", None)
        widget_classes = set(getattr(widget, "classes", set()))
        if "history-toggle" in widget_classes:
            event.stop()
            self.suppress_next_history_selection = True
            self.toggle_history_prompt_by_turn_index(getattr(widget, "name", ""))
            return
        if widget_id == "repo-path-info":
            event.stop()
            self.copy_project_path()
            return
        if widget_id == "todo-info":
            event.stop()
            self.toggle_todo_panel()
            return
        if widget_id == "stop-button" and self.is_generation_active():
            event.stop()
            self.stop_generation()

    def on_resize(self) -> None:
        self.enforce_output_scrollbars()
        self.update_composer_height()
        self.update_repo_path_info()
        self.position_output_metrics_caption()
        self.position_pacman_ghosts()
        self.position_ghost_clock()

    async def on_key(self, event) -> None:
        if self.history_expanded and event.key == "escape":
            event.prevent_default()
            event.stop()
            self.collapse_history()
            self.query_one("#prompt", TextArea).focus()
            return
        prompt_input = self.query_one("#prompt", TextArea)
        if self.history_expanded and event.key in {"up", "down"}:
            event.prevent_default()
            event.stop()
            self.move_history_selection(-1 if event.key == "up" else 1)
            return
        if self.history_expanded and event.character and event.character.isdigit():
            event.prevent_default()
            event.stop()
            self.pending_history_digit += event.character
            self.select_history_number()
            return
        if self.history_expanded and event.key == "enter":
            event.prevent_default()
            event.stop()
            history = self.query_one("#turn-history", ListView)
            await self.apply_history_selection(history.index or 0)
            return
        if event.key == "tab" and self.suggestion_values:
            event.prevent_default()
            event.stop()
            await self.apply_highlighted_suggestion(submit=False)
            return
        if event.key in {"up", "down"} and self.suggestion_values:
            event.prevent_default()
            event.stop()
            self.move_suggestion(-1 if event.key == "up" else 1)
            return
        if event.key == "escape" and self.suggestion_values:
            event.prevent_default()
            event.stop()
            self.hide_suggestions()
            prompt_input.focus()
            return
        if event.key == "enter" and self.suggestion_values:
            event.prevent_default()
            event.stop()
            await self.apply_highlighted_suggestion(submit=True)
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.submit_prompt()
            return
        if self.suggestion_mode == "models" and event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.suggestion_values):
                event.prevent_default()
                event.stop()
                await self.choose_model_suggestion(index)
                return

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "turn-history":
            event.stop()
            if self.suppress_next_history_selection:
                self.suppress_next_history_selection = False
                return
            if self.history_mode == "turns" and not self.history_expanded:
                self.history_pinned = True
                self.history_expanded = True
                self.refresh_history_panel_later()
                return
            await self.apply_history_selection(event.index)
            return
        if event.list_view.id != "suggestions":
            return
        event.stop()
        await self.apply_suggestion(event.index, submit=True)

    async def refresh_suggestions(self, value: str, cursor_position: int | None = None) -> None:
        context = slash_suggestion_context(value, len(value) if cursor_position is None else cursor_position)
        if context is None:
            self.hide_suggestions()
            return
        self.suggestion_start, self.suggestion_end, token = context
        stripped = value.strip()
        whole_token = value[: self.suggestion_start].strip() == "" and value[self.suggestion_end :].strip() == ""
        if whole_token and (stripped == "/model" or stripped.startswith("/model ")):
            selector = stripped.removeprefix("/model").strip()
            if selector and not selector.isdigit():
                self.hide_suggestions()
                return
            initial_index = int(selector) - 1 if selector.isdigit() else 0
            await self.show_model_suggestions(initial_index=initial_index)
            return
        matches = [(command, description) for command, description in self.COMMAND_CHOICES if command.startswith(token)]
        if not matches:
            self.hide_suggestions()
            return
        labels = [self.render_command_suggestion(command, description) for command, description in matches]
        await self.set_suggestions("commands", [command for command, _ in matches], labels)

    async def show_model_suggestions(self, initial_index: int = 0) -> None:
        models = list(local_available_models((self.ui.config.model.model,)))
        labels = [self.render_model_suggestion(index, model) for index, model in enumerate(models, start=1)]
        await self.set_suggestions("models", models, labels, initial_index=initial_index)

    async def set_suggestions(self, mode: str, values: list[str], labels: list[str], initial_index: int = 0) -> None:
        self.suggestion_mode = mode
        self.suggestion_values = values
        suggestions = self.query_one("#suggestions", ListView)
        await suggestions.clear()
        for label in labels:
            await suggestions.append(ListItem(Static(label)))
        suggestions.index = min(max(initial_index, 0), len(values) - 1) if values else None
        suggestions.styles.display = "block" if values else "none"
        self.position_suggestions(len(values))

    def hide_suggestions(self) -> None:
        self.suggestion_mode = None
        self.suggestion_values = []
        self.suggestion_start = 0
        self.suggestion_end = 0
        suggestions = self.query_one("#suggestions", ListView)
        suggestions.styles.display = "none"
        suggestions.styles.offset = (0, 0)

    def position_suggestions(self, value_count: int) -> None:
        suggestions = self.query_one("#suggestions", ListView)
        suggestions.styles.offset = (0, 0)
        suggestions.styles.width = min(76, max(24, self.size.width - 4))
        self.update_popup_margins()

    def move_suggestion(self, delta: int) -> None:
        suggestions = self.query_one("#suggestions", ListView)
        if not self.suggestion_values:
            return
        current = suggestions.index or 0
        suggestions.index = (current + delta) % len(self.suggestion_values)

    async def apply_highlighted_suggestion(self, submit: bool) -> None:
        suggestions = self.query_one("#suggestions", ListView)
        await self.apply_suggestion(suggestions.index or 0, submit=submit)

    async def apply_suggestion(self, index: int, submit: bool) -> None:
        if not 0 <= index < len(self.suggestion_values):
            return
        if self.suggestion_mode == "models":
            await self.choose_model_suggestion(index)
            return

        command = self.suggestion_values[index]
        prompt_input = self.query_one("#prompt", TextArea)
        embedded = not self.suggestion_covers_whole_input(prompt_input.text)
        if command == "/model" and not embedded:
            self.set_prompt_value(prompt_input, "/model ")
            prompt_input.focus()
            await self.show_model_suggestions()
            return
        if not submit:
            value = f"{command} " if command in self.ARG_COMMANDS else command
            self.replace_suggestion_token(prompt_input, value)
            prompt_input.focus()
            self.hide_suggestions()
            return
        if embedded:
            self.replace_suggestion_token(prompt_input, command)
            self.hide_suggestions()
            raw = prompt_input.text.strip()
            self.clear_prompt(prompt_input)
            self.process_raw(raw)
            return
        self.hide_suggestions()
        self.clear_prompt(prompt_input)
        self.process_raw(command)

    def suggestion_covers_whole_input(self, value: str) -> bool:
        if not value:
            return True
        return value[: self.suggestion_start].strip() == "" and value[self.suggestion_end :].strip() == ""

    def replace_suggestion_token(self, prompt_input: TextArea, replacement: str) -> None:
        value = prompt_input.text
        start = max(0, min(self.suggestion_start, len(value)))
        end = max(start, min(self.suggestion_end, len(value)))
        new_value = f"{value[:start]}{replacement}{value[end:]}"
        self.set_prompt_value(prompt_input, new_value, cursor_index=start + len(replacement))

    async def choose_model_suggestion(self, index: int) -> None:
        model_number = index + 1
        self.hide_suggestions()
        prompt_input = self.query_one("#prompt", TextArea)
        self.clear_prompt(prompt_input)
        self.process_raw(f"/model {model_number}")

    def submit_prompt(self) -> None:
        prompt_input = self.query_one("#prompt", TextArea)
        raw = prompt_input.text.strip()
        if not raw:
            self.clear_prompt(prompt_input)
            return
        if self.is_generation_active():
            self.show_notice("↳ Model is busy. Finish the current response before submitting another prompt.")
            return
        self.hide_suggestions()
        self.clear_prompt(prompt_input)
        self.process_raw(raw)

    def clear_prompt(self, prompt_input: TextArea) -> None:
        self.set_prompt_value(prompt_input, "")

    def set_prompt_value(self, prompt_input: TextArea, value: str, cursor_index: int | None = None) -> None:
        prompt_input.load_text(value)
        prompt_input.move_cursor(text_index_to_location(value, len(value) if cursor_index is None else cursor_index))
        self.update_composer_height()

    def prompt_cursor_index(self, prompt_input: TextArea) -> int:
        return location_to_text_index(prompt_input.text, prompt_input.cursor_location)

    def update_composer_height(self) -> None:
        try:
            prompt_input = self.query_one("#prompt", TextArea)
            prompt_row = self.query_one("#prompt-row", Horizontal)
            composer = self.query_one("#composer", Vertical)
        except Exception:
            return
        total_lines = self.prompt_visual_line_count(prompt_input.text)
        visible_lines = min(self.PROMPT_MAX_LINES, max(1, total_lines))
        prompt_input.styles.height = visible_lines
        prompt_row.styles.height = visible_lines
        composer.styles.height = visible_lines + 2
        prompt_input.show_vertical_scrollbar = total_lines > self.PROMPT_MAX_LINES
        prompt_input.show_horizontal_scrollbar = False
        prompt_input.styles.scrollbar_size_horizontal = 0
        self.update_popup_margins()

    def prompt_visual_line_count(self, text: str) -> int:
        width = self.prompt_wrap_width()
        return prompt_visual_line_count(text, width)

    def prompt_wrap_width(self) -> int:
        try:
            prompt_input = self.query_one("#prompt", TextArea)
        except Exception:
            return 72
        width = prompt_input.content_size.width or prompt_input.size.width or 72
        return max(8, width - 1)

    def update_popup_margins(self) -> None:
        try:
            composer = self.query_one("#composer", Vertical)
            suggestions = self.query_one("#suggestions", ListView)
            notice = self.query_one("#notice", Static)
            thinking = self.query_one("#thinking", Static)
            ghosts = self.query_one("#pacman-ghosts", Static)
            run_control = self.query_one("#run-control", Horizontal)
        except Exception:
            return
        composer_height = composer.styles.height.value if hasattr(composer.styles.height, "value") else composer.size.height or 3
        composer_height = int(composer_height or 3)
        suggestions.styles.margin = (0, 2, composer_height + 1, 2)
        notice.styles.margin = (0, 2, composer_height + 1, 2)
        thinking.styles.margin = (0, 2, composer_height, 2)
        ghosts.styles.margin = (0, 0, composer_height, 0)
        run_control.styles.margin = (0, 0, composer_height, 0)

    def render_command_suggestion(self, command: str, description: str) -> str:
        return f"[#aee4fc]{command:<10}[/] [#8d93a1]{_escape_markup(_single_line(description, max_chars=54))}[/]"

    def render_model_suggestion(self, index: int, model: str) -> str:
        marker = "current" if model == self.ui.config.model.model else "available"
        return f"[#ffe45c]{index}[/]  {_escape_markup(compact_model_name(model, max_chars=54))}  [#8d93a1]{marker}[/]"

    def action_clear_log(self) -> None:
        self.query_one("#log", TranscriptView).clear()
        self.clear_output_metrics_caption()
        self.reset_output_buffer()

    def action_toggle_history(self) -> None:
        self.history_pinned = not self.history_pinned
        self.history_expanded = self.history_pinned
        self.refresh_history_panel_later()

    def collapse_history(self) -> None:
        self.history_pinned = False
        self.history_expanded = False
        self.expanded_turn_prompts.clear()
        self.pending_history_digit = ""
        self.refresh_history_panel_later()

    def copy_project_path(self) -> None:
        self.copy_to_clipboard(str(self.ui.config.project.root))
        self.query_one("#thinking", Static).update("✓ Copied project path")

    def copy_to_clipboard(self, text: str) -> None:
        super().copy_to_clipboard(text)
        self.copy_notice_until = time.monotonic() + 1.5
        if self.thinking_started_at is None:
            self.query_one("#thinking", Static).update("✓ Copied selection")

    def auto_copy_selection(self) -> None:
        if self.query_one("#git-status-info", Static).is_mouse_over:
            return
        selection = self.screen.get_selected_text()
        if not selection:
            self.last_copied_selection = ""
            return
        if selection == self.last_copied_selection:
            return
        self.last_copied_selection = selection
        self.copy_to_clipboard(selection)

    def start_new_turn(self, raw: str) -> None:
        timestamp = current_time_label()
        self.current_turn_index = self.history_model.add_turn(TurnRecord(prompt=raw, timestamp=timestamp, created_at=time.time()))
        self.history_mode = "turns"
        self.expanded_turn_prompts.clear()
        self.measured_context_tokens = None
        self.reset_output_box(raw, timestamp)
        self.query_one("#log", TranscriptView).consume(UserPrompt(text=raw, timestamp=timestamp))
        self.refresh_history_panel_later()

    def reset_output_box(self, raw: str, timestamp: str) -> None:
        log = self.query_one("#log", TranscriptView)
        log.clear()
        log.border_title = ""
        log.border_subtitle = ""
        self.clear_output_metrics_caption()
        self.reset_output_buffer()

    def update_current_turn_output(self) -> None:
        if self.current_turn_index is None:
            return
        if not 0 <= self.current_turn_index < len(self.turn_records):
            return
        self.turn_records[self.current_turn_index].output = self.output_raw_text

    def refresh_history_panel_later(self) -> None:
        if not self.is_mounted or not self.is_running:
            return
        try:
            history = self.query_one("#turn-history", ListView)
        except Exception:
            return
        if not history.is_mounted:
            return
        self.run_worker(
            self.refresh_history_panel(),
            name="history-panel",
            group="history-panel",
            exclusive=True,
            exit_on_error=False,
        )

    async def refresh_history_panel(self) -> None:
        try:
            history = self.query_one("#turn-history", ListView)
        except Exception:
            return
        if not history.is_mounted:
            return
        try:
            history.border_title = " Turns "
            history.border_subtitle = ""
            await history.clear()
            if self.history_mode == "sessions":
                self.session_choices = self.ui.session_store.recent_session_ids(limit=8)
                await history.append(self.history_item("[#b897ff]Current conversation[/]"))
                if not self.session_choices:
                    await history.append(self.history_item("[#8d93a1]No saved sessions[/]"))
                    history.index = 0
                    return
                for index, session_id in enumerate(self.session_choices, start=1):
                    preview = self.session_preview(session_id)
                    await history.append(
                        self.history_item(f"[#ffe45c]{index}[/]  {session_id}  [#8d93a1]{_escape_markup(preview)}[/]")
                    )
                history.index = 0
                return

            visible_records = list(enumerate(self.turn_records, start=1))
            if not self.history_expanded and visible_records:
                selected_index = self.current_turn_index if self.current_turn_index is not None else len(self.turn_records) - 1
                selected_index = max(0, min(selected_index, len(self.turn_records) - 1))
                visible_records = [(selected_index + 1, self.turn_records[selected_index])]
            if not visible_records:
                await history.append(self.history_item("[#8d93a1]No turns yet[/]"))
                history.index = 0
                return
            for index, record in visible_records:
                await history.append(self.history_record_item(index, record))
            history.index = len(visible_records) - 1
        except Exception:
            return

    def history_item(self, label: str, tooltip: str | None = None) -> ListItem:
        static = Static(label)
        if tooltip:
            static.tooltip = tooltip
        item = ListItem(static)
        if tooltip:
            item.tooltip = tooltip
        return item

    def history_record_item(self, index: int, record: TurnRecord) -> ListItem:
        tooltip = _exact_time_label(record.created_at)
        expanded = index - 1 in self.expanded_turn_prompts
        expandable = self.history_prompt_needs_expansion(record)
        row = self.history_record_expanded(index, record) if expanded else self.history_record_row(index, record, expandable=expandable)
        row.tooltip = tooltip
        item = ListItem(row)
        item.tooltip = tooltip
        return item

    def history_record_row(self, index: int, record: TurnRecord, expandable: bool = False) -> Horizontal:
        relative = _relative_time_label(record.created_at)
        toggle = "▸" if expandable else " "
        prompt_width = max(8, self.history_label_width() - cell_len(relative) - 10)
        prompt = _single_line(record.prompt.replace("\n", " "), max_chars=prompt_width)
        return Horizontal(
            Static(
                self.history_toggle_label(index, expanded=False) if expandable else self.history_index_label(index),
                name=str(index - 1),
                classes="history-toggle" if expandable else "history-index",
            ),
            Static(_escape_markup(prompt), classes="history-prompt"),
            Static(relative, classes="history-time"),
            classes="history-row",
        )

    def history_record_expanded(self, index: int, record: TurnRecord) -> Vertical:
        relative = _relative_time_label(record.created_at)
        width = self.history_label_width()
        prompt_width = max(8, width - cell_len(relative) - 10)
        wrapped_lines = wrap_plain_text(record.prompt, prompt_width)
        first_line = wrapped_lines[0] if wrapped_lines else ""
        rows = [
            Horizontal(
                Static(self.history_toggle_label(index, expanded=True), name=str(index - 1), classes="history-toggle"),
                Static(_escape_markup(first_line), classes="history-prompt"),
                Static(relative, classes="history-time"),
                classes="history-row",
            )
        ]
        rows.extend(
            Horizontal(
                Static(self.history_toggle_label(index, expanded=True), classes="history-toggle-placeholder"),
                Static(_escape_markup(line), classes="history-prompt"),
                classes="history-row",
            )
            for line in wrapped_lines[1:]
        )
        return Vertical(*rows)

    def history_toggle_label(self, index: int, expanded: bool = False) -> str:
        return history_toggle_label(index, expanded)

    def history_index_label(self, index: int) -> str:
        return history_index_label(index)

    def toggle_history_prompt_by_turn_index(self, turn_index_value) -> bool:
        try:
            turn_index = int(turn_index_value)
        except (TypeError, ValueError):
            return False
        if not 0 <= turn_index < len(self.turn_records):
            return False
        if not self.history_model.toggle_prompt(turn_index, max_prompt_chars=self.history_max_prompt_chars(self.turn_records[turn_index])):
            return False
        self.refresh_history_panel_later()
        return True

    def history_prompt_needs_expansion(self, record: TurnRecord) -> bool:
        return prompt_needs_expansion(record.prompt, self.history_max_prompt_chars(record))

    def history_max_prompt_chars(self, record: TurnRecord) -> int:
        width = self.history_label_width()
        relative = _relative_time_label(record.created_at)
        prefix = "▸ 1  "
        return max(8, width - cell_len(prefix) - cell_len(relative) - 2)

    def history_label_width(self) -> int:
        try:
            history = self.query_one("#turn-history", ListView)
        except Exception:
            return 80
        return max(32, history.content_size.width or history.size.width or 80)

    def move_history_selection(self, delta: int) -> None:
        history = self.query_one("#turn-history", ListView)
        item_count = len(history.children)
        if item_count <= 0:
            return
        current = history.index or 0
        history.index = (current + delta) % item_count

    def select_history_number(self) -> None:
        if not self.pending_history_digit:
            return
        index = int(self.pending_history_digit) - 1
        history = self.query_one("#turn-history", ListView)
        if 0 <= index < len(history.children):
            history.index = index
        self.pending_history_digit = ""

    def session_preview(self, session_id: str) -> str:
        events = self.ui.session_store.events_for(session_id)
        first_user = next((event.text for event in events if event.kind == "user"), "")
        return _single_line(first_user, max_chars=44) if first_user else "(no user prompt)"

    async def apply_history_selection(self, index: int) -> None:
        if self.is_generation_active():
            self.query_one("#thinking", Static).update("↳ History preview is paused until the current response finishes.")
            return
        if self.history_mode == "sessions":
            if index == 0:
                self.history_mode = "turns"
                await self.refresh_history_panel()
                return
            session_index = index - 1
            if not 0 <= session_index < len(self.session_choices):
                return
            session_id = self.session_choices[session_index]
            self.show_output_snapshot(f"Session {session_id}", self.ui.session_store.format_transcript(session_id))
            return

        turn_index = index if self.history_expanded else len(self.turn_records) - 1
        if not 0 <= turn_index < len(self.turn_records):
            return
        record = self.turn_records[turn_index]
        self.current_turn_index = turn_index
        self.history_model.current_turn_index = turn_index
        self.measured_context_tokens = record.context_tokens
        self.show_output_snapshot(record.prompt, record.output or "(no output yet)", record.metrics, record.metrics_detail)
        self.history_pinned = False
        self.history_expanded = False
        self.expanded_turn_prompts.clear()
        self.refresh_history_panel_later()

    def show_output_snapshot(self, title: str, output: str, metrics: str = "", metrics_detail: str = "") -> None:
        self.set_chat_visible(True)
        log = self.query_one("#log", TranscriptView)
        log.clear()
        log.border_title = ""
        log.border_subtitle = ""
        self.update_output_metrics_caption(metrics, metrics_detail)
        self.output_raw_text = output.rstrip() + "\n\n"
        log.consume(Summary(title=title, body=output.rstrip()))
        self.update_topbar_status()

    def is_llm_request(self, raw: str) -> bool:
        return bool(raw and (not raw.startswith("/") or raw.startswith("/ask ")))

    def is_generation_active(self) -> bool:
        return self.thinking_started_at is not None or self.responding_started_at is not None

    def start_llm_request(self, raw: str) -> None:
        prompt = raw.removeprefix("/ask ").strip() if raw.startswith("/ask ") else raw
        self.next_generation_id += 1
        generation_id = self.next_generation_id
        self.active_generation_id = generation_id
        self.generation_cancel_requested = False
        self.thinking_started_at = time.monotonic()
        self.responding_started_at = None
        self.thinking_prompt = prompt
        self.thinking_context_tokens = estimate_context_tokens(prompt)
        self.spinner_index = 0
        self.update_thinking_status()
        threading.Thread(target=self.run_llm_request, args=(generation_id, raw), daemon=True).start()

    def run_llm_request(self, generation_id: int, raw: str) -> None:
        try:
            response = self.ui.dispatch(raw, record=False)
            self.call_from_thread(self.finish_llm_request, generation_id, raw, response, None)
        except Exception as exc:
            self.call_from_thread(self.finish_llm_request, generation_id, raw, None, exc)

    def finish_llm_request(
        self,
        generation_id: int,
        raw: str,
        response: TUIResponse | None,
        exc: Exception | None,
    ) -> None:
        if generation_id != self.active_generation_id:
            self.cancelled_generation_ids.discard(generation_id)
            return
        if generation_id in self.cancelled_generation_ids:
            self.cancelled_generation_ids.discard(generation_id)
            self.finish_generation_cancel()
            return
        self.thinking_started_at = None
        self.thinking_prompt = ""
        self.thinking_context_tokens = 0
        if self.generation_cancel_requested:
            self.finish_generation_cancel()
            return
        if exc is not None:
            self.write_output(f"ERROR: {exc}")
            self.finish_response_stream()
        elif response is not None and response.output:
            self.sync_config_from_ui()
            self.ui.record_exchange(raw, response.output)
            self.start_response_stream(response.output, response.should_continue)
            return
        else:
            if response is not None:
                self.ui.record_exchange(raw)
            self.finish_response_stream()

    def update_thinking_status(self) -> None:
        self.update_notice_status()
        if self.responding_started_at is not None:
            elapsed = time.monotonic() - self.responding_started_at
            frame = self.ARC_SPINNER_FRAMES[self.spinner_index % len(self.ARC_SPINNER_FRAMES)]
            self.spinner_index += 1
            self.query_one("#thinking", Static).update(f"{frame} Responding... {elapsed:.1f}s")
            self.update_run_control()
            return
        if self.thinking_started_at is None:
            if self.copy_notice_until and time.monotonic() > self.copy_notice_until:
                self.copy_notice_until = 0.0
                self.hide_thinking_status()
            return
        elapsed = time.monotonic() - self.thinking_started_at
        frame = self.SPINNER_FRAMES[self.spinner_index % len(self.SPINNER_FRAMES)]
        self.spinner_index += 1
        self.query_one("#thinking", Static).update(f"{frame} Thinking... {elapsed:.1f}s")
        self.update_run_control()

    def hide_thinking_status(self) -> None:
        self.query_one("#thinking", Static).update("")
        self.update_run_control()

    def show_notice(self, message: str, seconds: float = 2.0) -> None:
        self.notice_until = time.monotonic() + seconds
        self.query_one("#notice", Static).update(message)

    def update_notice_status(self) -> None:
        if self.notice_until and time.monotonic() > self.notice_until:
            self.notice_until = 0.0
            self.query_one("#notice", Static).update("")

    def write_output(self, output: str) -> None:
        body, metrics, metrics_detail = split_output_metrics_detail(output)
        if metrics:
            self.set_output_metrics(metrics, metrics_detail)
        self.write_transcript_output(body.rstrip(), metrics, metrics_detail)

    def start_response_stream(self, output: str, should_continue: bool) -> None:
        body, metrics, metrics_detail = split_output_metrics_detail(output)
        if metrics:
            self.set_output_metrics(metrics, metrics_detail)
        self.response_text = body.rstrip() + "\n\n"
        self.response_index = 0
        self.response_should_continue = should_continue
        self.responding_started_at = time.monotonic()
        self.response_last_tick = self.responding_started_at
        self.stream_controller.reset()
        self.update_run_control()
        self.update_response_stream()

    def set_output_metrics(self, metrics: str, metrics_detail: str = "") -> None:
        self.query_one("#log", TranscriptView).border_subtitle = ""
        self.update_output_metrics_caption(metrics, metrics_detail)
        context_tokens = parse_context_metric_tokens(metrics_detail)
        if context_tokens is not None:
            self.measured_context_tokens = context_tokens
            self.update_context_info()
        if self.current_turn_index is None:
            return
        if not 0 <= self.current_turn_index < len(self.turn_records):
            return
        self.turn_records[self.current_turn_index].metrics = metrics
        self.turn_records[self.current_turn_index].metrics_detail = metrics_detail
        self.turn_records[self.current_turn_index].context_tokens = context_tokens

    def update_output_metrics_caption(self, metrics: str, metrics_detail: str = "") -> None:
        self.output_metrics_text = metrics
        self.output_metrics_detail = metrics_detail
        caption = self.query_one("#output-metrics", Static)
        caption.update(f" {self.output_metrics_display_text()} " if metrics else "")
        caption.tooltip = metrics_detail or None
        self.refresh_output_metrics_visibility()

    def clear_output_metrics_caption(self) -> None:
        self.update_output_metrics_caption("", "")

    def refresh_output_metrics_visibility(self) -> None:
        caption = self.query_one("#output-metrics", Static)
        log_visible = self.query_one("#log", TranscriptView).styles.display != "none"
        caption.styles.display = "block" if log_visible and self.output_metrics_text else "none"
        self.position_output_metrics_caption()

    def output_metrics_display_text(self) -> str:
        max_chars = max(18, self.size.width - 12)
        return _single_line(self.output_metrics_text, max_chars=max_chars)

    def position_output_metrics_caption(self) -> None:
        try:
            caption = self.query_one("#output-metrics", Static)
        except Exception:
            return
        text_width = cell_len(f" {self.output_metrics_display_text()} ") if self.output_metrics_text else 0
        offset_x = max(2, self.size.width - text_width - 5) if text_width else 0
        caption.styles.offset = (offset_x, 0)

    def animate_pacman_ghosts(self) -> None:
        self.ghost_frame += 1
        ghosts = self.query_one("#pacman-ghosts", Static)
        ghosts.update(self.render_pacman_ghosts())
        self.position_pacman_ghosts()

    def render_pacman_ghosts(self) -> str:
        return pacman_ghost_frame(self.ghost_frame, max_spaces=self.GHOST_TRACK_SPACES)

    def position_pacman_ghosts(self) -> None:
        try:
            ghosts = self.query_one("#pacman-ghosts", Static)
        except Exception:
            return
        ghosts.styles.offset = (max(2, self.run_control_offset_x() - self.GHOST_WIDTH - 1), 0)

    def update_ghost_clock(self) -> None:
        self.update_run_control()

    def update_run_control(self) -> None:
        try:
            token_counter = self.query_one("#token-counter", Static)
            stop_button = self.query_one("#stop-button", Static)
        except Exception:
            return
        if self.responding_started_at is not None:
            current_tokens = estimate_context_tokens(self.response_text[: self.response_index])
            total_tokens = estimate_context_tokens(self.response_text)
            token_counter.update(f"↓{_format_token_count(current_tokens)}/{_format_token_count(total_tokens)}")
            stop_button.styles.display = "block"
        elif self.thinking_started_at is not None:
            token_counter.update(f"↑{_format_token_count(self.thinking_context_tokens)}")
            stop_button.styles.display = "block"
        else:
            token_counter.update(current_time_label())
            stop_button.styles.display = "none"
        self.position_ghost_clock()

    def position_ghost_clock(self) -> None:
        try:
            run_control = self.query_one("#run-control", Horizontal)
        except Exception:
            return
        run_control.styles.offset = (self.run_control_offset_x(), 0)

    def run_control_offset_x(self) -> int:
        try:
            composer = self.query_one("#composer", Vertical)
            run_control = self.query_one("#run-control", Horizontal)
        except Exception:
            return max(2, self.size.width - self.RUN_CONTROL_WIDTH - 2)
        composer_right = composer.region.x + composer.region.width
        run_width = run_control.region.width or run_control.size.width or self.RUN_CONTROL_WIDTH
        return max(2, composer_right - run_width)

    def update_response_stream(self) -> None:
        if self.responding_started_at is None or not self.response_text:
            return
        if self.generation_cancel_requested:
            self.finish_generation_cancel()
            return
        now = time.monotonic()
        elapsed_since_tick = max(0.0, now - self.response_last_tick)
        chars_to_write = max(1, int(elapsed_since_tick / self.RESPONSE_STREAM_SECONDS_PER_CHAR))
        if chars_to_write <= 0:
            return
        self.response_last_tick = now
        end = min(len(self.response_text), self.response_index + chars_to_write)
        chunk = self.response_text[self.response_index:end]
        self.response_index = end
        self.stream_controller.append(chunk)
        if self.stream_controller.should_flush(now):
            self.flush_response_stream(now)
        if self.response_index >= len(self.response_text):
            self.flush_response_stream(now)
            self.finish_response_stream()

    def write_transcript_output(self, body: str, metrics: str = "", metrics_detail: str = "") -> None:
        transcript = self.query_one("#log", TranscriptView)
        prompt = self.turn_records[self.current_turn_index].prompt if self.current_turn_index is not None else ""
        if body.startswith("ERROR:"):
            transcript.consume(Error(message=body))
        elif body.startswith("Unknown command."):
            transcript.consume(Error(message=body))
        elif prompt.startswith("/index"):
            transcript.consume(ToolCallStarted(name="index", args={"prompt": prompt}))
            transcript.consume(Summary(title="Index", body=body))
        elif prompt.startswith("/yaml"):
            transcript.consume(ToolCallStarted(name="yaml", args={"prompt": prompt}))
            transcript.consume(ToolResult(name="yaml", output=body))
        elif prompt.startswith("/explain"):
            transcript.consume(ToolCallStarted(name="explain", args={"prompt": prompt}))
            transcript.consume(ToolResult(name="explain", output=body))
        else:
            transcript.consume(AssistantTextDelta(text=body + "\n\n"))
            transcript.consume(AssistantTextEnd())
        if metrics:
            transcript.consume(Metrics(summary=metrics, detail=metrics_detail))
        self.output_raw_text += body.rstrip() + "\n\n"
        self.update_current_turn_output()
        self.update_topbar_status()

    def emit_assistant_delta(self, text: str) -> None:
        self.output_raw_text += text
        self.query_one("#log", TranscriptView).consume(AssistantTextDelta(text=text))
        self.update_run_control()
        self.update_current_turn_output()
        self.update_topbar_status()

    def flush_response_stream(self, now: float | None = None) -> None:
        chunk = self.stream_controller.flush(now)
        if chunk:
            self.emit_assistant_delta(chunk)

    def reset_output_buffer(self) -> None:
        self.output_raw_text = ""
        self.stream_controller.reset()

    def enforce_output_scrollbars(self) -> None:
        log = self.query_one("#log", TranscriptView)
        log.show_horizontal_scrollbar = False
        log.styles.scrollbar_size_horizontal = 0

    def finish_response_stream(self) -> None:
        should_continue = self.response_should_continue
        self.query_one("#log", TranscriptView).consume(AssistantTextEnd())
        if self.output_metrics_text:
            self.query_one("#log", TranscriptView).consume(Metrics(summary=self.output_metrics_text, detail=self.output_metrics_detail))
        self.responding_started_at = None
        self.response_text = ""
        self.response_index = 0
        self.active_generation_id = None
        self.generation_cancel_requested = False
        prompt_input = self.query_one("#prompt", TextArea)
        prompt_input.focus()
        self.hide_thinking_status()
        self.update_run_control()
        if not should_continue:
            self.exit()

    def stop_generation(self) -> None:
        if not self.is_generation_active():
            return
        generation_id = self.active_generation_id
        if generation_id is not None:
            self.cancelled_generation_ids.add(generation_id)
        self.generation_cancel_requested = True
        if self.responding_started_at is not None:
            self.finish_generation_cancel()
            return
        self.active_generation_id = None
        self.generation_cancel_requested = False
        self.thinking_started_at = None
        self.thinking_prompt = ""
        self.thinking_context_tokens = 0
        self.hide_thinking_status()

    def finish_generation_cancel(self) -> None:
        self.responding_started_at = None
        self.response_text = ""
        self.response_index = 0
        self.stream_controller.reset()
        if self.active_generation_id is not None:
            self.cancelled_generation_ids.discard(self.active_generation_id)
        self.active_generation_id = None
        self.generation_cancel_requested = False
        self.hide_thinking_status()
        try:
            self.query_one("#prompt", TextArea).focus()
        except Exception:
            return

    def render_git_status_info(self) -> str:
        git_info = get_git_info(self.ui.config.project.root)
        branch = git_info.branch or self.ui.config.project.name
        parts = [f"[#7d8492]⎇[/] [#8d93a1]{_escape_markup(branch)}[/]"]
        if git_info.is_worktree:
            parts.append("[#b897ff]worktree[/]")
        return " ".join(parts) + " "

    def render_repo_path_info(self) -> str:
        git_info = get_git_info(self.ui.config.project.root)
        path = _compact_middle_path(_home_relative_path(self.ui.config.project.root), self.repo_path_max_chars())
        suffix = ""
        if git_info.is_worktree and git_info.main_worktree is not None:
            worktree = _compact_middle_path(_home_relative_path(git_info.main_worktree), max(18, self.repo_path_max_chars() // 2))
            suffix = f" [#6f7785](worktree of {_escape_markup(worktree)})[/]"
        return f"{_escape_markup(path)}{suffix}"

    def repo_path_max_chars(self) -> int:
        try:
            widget = self.query_one("#repo-path-info", Static)
        except Exception:
            return 56
        width = widget.content_size.width or widget.size.width or 56
        return max(18, min(72, width - 1))

    def update_repo_path_info(self) -> None:
        self.query_one("#repo-path-info", Static).update(self.render_repo_path_info())

    def render_context_info(self):
        tokens = self.current_context_tokens()
        context_info = self.query_one("#context-info", Static)
        if context_info.is_mouse_over:
            return self.render_context_progress(tokens)
        label = f"{_format_token_count(tokens)} / {_format_token_count(self.CONTEXT_LIMIT_TOKENS)}"
        return label.rjust(self.context_info_width())

    def render_context_progress(self, tokens: int) -> Text:
        width = self.context_info_width()
        ratio = min(1.0, max(0.0, tokens / self.CONTEXT_LIMIT_TOKENS))
        label = f"{ratio * 100:.2f}%"
        text = Text(label.rjust(width), style="#e6e8eb")
        progress_cells = min(width, round(width * ratio))
        if progress_cells:
            text.stylize("on #4A3F13", 0, progress_cells)
        return text

    def context_info_width(self) -> int:
        try:
            context_info = self.query_one("#context-info", Static)
        except Exception:
            return 12
        width = context_info.content_size.width or context_info.size.width or 12
        return max(12, width)

    def render_todo_info(self) -> str:
        done = 0
        total = len(self.todo_items)
        chevron = "⌃" if self.todo_panel_open else "⌄"
        return f"{done} {total} {chevron}"

    def render_todo_panel(self) -> str:
        if not self.todo_items:
            return "\n".join(
                [
                    "[#8d93a1]To-do list[/]",
                    "No active tasks yet.",
                    "Future agent planning will populate this before each LLM call.",
                ]
            )
        lines = ["[#8d93a1]To-do list[/]"]
        lines.extend(f"[ ] {_escape_markup(item)}" for item in self.todo_items)
        return "\n".join(lines)

    def current_context_tokens(self) -> int:
        if self.measured_context_tokens is not None and not self.thinking_prompt:
            return self.measured_context_tokens
        text = "\n".join(part for part in (self.output_raw_text, self.thinking_prompt) if part)
        return estimate_context_tokens(text)

    def update_topbar_status(self) -> None:
        self.update_context_info()

        todo_info = self.query_one("#todo-info", Static)
        todo_info.update(self.render_todo_info())
        todo_info.tooltip = "Click to show the Jarvis-Agent to-do list."

    def update_context_info(self) -> None:
        context_info = self.query_one("#context-info", Static)
        context_info.update(self.render_context_info())
        context_info.tooltip = None

    def toggle_todo_panel(self) -> None:
        self.todo_panel_open = not self.todo_panel_open
        panel = self.query_one("#todo-panel", Static)
        panel.update(self.render_todo_panel())
        panel.styles.display = "block" if self.todo_panel_open else "none"
        self.update_topbar_status()

    def hide_todo_panel(self) -> None:
        self.todo_panel_open = False
        self.query_one("#todo-panel", Static).styles.display = "none"
        self.update_topbar_status()

    def render_model_info(self) -> str:
        return f"{model_badge_name(self.ui.config.model.model)} · {self.ui.config.model.backend}"

    def sync_config_from_ui(self) -> None:
        self.agent_config = self.ui.config
        self.query_one("#git-status-info", Static).update(self.render_git_status_info())
        self.update_repo_path_info()
        self.update_topbar_status()
        self.update_composer_caption()
        self.query_one("#home-panel", Static).update(self.render_home_panel())

    def update_composer_caption(self) -> None:
        self.query_one("#composer", Vertical).border_subtitle = f" {self.render_model_info()} "

    def show_home(self) -> None:
        self.splash_frame = 0
        self.home_visible = True
        self.set_chat_visible(False)
        hero = self.query_one("#hero", Horizontal)
        hero.styles.display = "block"
        self.query_one("#home-panel", Static).update(self.render_home_panel())
        self.update_logo_monitor()

    def hide_home(self) -> None:
        self.home_visible = False
        self.query_one("#hero", Horizontal).styles.display = "none"
        self.set_chat_visible(True)

    def set_chat_visible(self, visible: bool) -> None:
        display = "block" if visible else "none"
        self.query_one("#turn-history", ListView).styles.display = display
        self.query_one("#log", TranscriptView).styles.display = display
        self.query_one("#notice", Static).styles.display = display
        self.query_one("#thinking", Static).styles.display = display
        self.refresh_output_metrics_visibility()

    def animate_home(self) -> None:
        if not self.home_visible:
            return
        max_frame = self.LOGO_MONITOR.reveal_frames + self.LOGO_MONITOR.monitor_frames
        self.splash_frame = min(self.splash_frame + 1, max_frame)
        self.update_logo_monitor()

    def update_logo_monitor(self) -> None:
        self.query_one("#logo-monitor", Static).update(self.render_logo_monitor_frame())

    def render_logo_monitor_frame(self) -> str:
        return render_logo_monitor_frame(
            self.splash_frame,
            self.ui.branding.logo_pattern,
            self.ui.branding.logo_widths("left"),
            self.ui.branding.logo_widths("right"),
            self.LOGO_MONITOR,
        )

    def render_home_panel(self) -> str:
        lines = [
            *self.render_colored_version_lines(self.ui.branding.compact_version_lines()),
            "",
            "[#ffe45c bold]Jarvis-Agent local HEP composer[/]",
            "Index packages, explain source, review YAML, and ask local MLX models.",
            "",
            f"Project: {self.ui.config.project.root}",
            f"Model: {self.ui.config.model.backend}:{self.ui.config.model.model}",
            f"History: {self.ui.session_store.path}",
            "",
            "[bold]Start[/]                    [#8d93a1]Command[/]",
            "Index package             /index",
            "Review YAML               /yaml path.yaml",
            "Explain source            /explain path/to/file",
            "Choose model              /model",
            "Resume session            /resume",
            "Quit                      /quit",
        ]
        return "\n".join(lines)

    def render_colored_version_lines(self, lines: tuple[str, ...]) -> list[str]:
        rendered: list[str] = []
        for index, line in enumerate(lines):
            escaped = _escape_markup(line)
            if index < len(TEXT_GRADIENT_COLORS):
                style = " bold" if "Just a Robust" in line or "Author:" in line or "Version:" in line else ""
                rendered.append(f"[{TEXT_GRADIENT_COLORS[index]}{style}]{escaped}[/]")
            else:
                rendered.append(escaped)
        return rendered




def run_textual_ui(config: AgentConfig) -> int:
    JarvisAgentApp(config).run()
    return 0
