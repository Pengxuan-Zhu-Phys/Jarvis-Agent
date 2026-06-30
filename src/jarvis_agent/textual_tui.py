from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import subprocess
import threading
import time

from rich.cells import cell_len

from jarvis_agent.branding import TEXT_GRADIENT_COLORS
from jarvis_agent.config import AVAILABLE_MODELS, AgentConfig, compact_model_name, model_badge_name
from jarvis_agent.tui import TUIResponse, TerminalUI


class TextualUnavailable(RuntimeError):
    """Raised when the optional Textual dependency is not installed."""


@dataclass(frozen=True)
class GitInfo:
    branch: str = ""
    is_worktree: bool = False
    main_worktree: Path | None = None


@dataclass
class TurnRecord:
    prompt: str
    timestamp: str
    created_at: float
    output: str = ""
    metrics: str = ""
    metrics_detail: str = ""


def run_textual_ui(config: AgentConfig) -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Input, ListItem, ListView, Log, Static
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TextualUnavailable("Textual is not installed. Install with: pip install -e '.[tui]'") from exc

    class JarvisAgentApp(App[None]):
        CONTEXT_LIMIT_TOKENS = 200_000
        HISTOGRAM_ROWS = 8
        HISTOGRAM_COLS = 4
        SPLASH_REVEAL_FRAMES = 8
        SPLASH_MONITOR_FRAMES = 18
        SPLASH_HOLD_FRAMES = 14
        LEFT_MONITOR_SERIES = (
            (1, 2, 1, 3, 2, 4, 1, 2),
            (2, 1, 3, 2, 4, 2, 3, 1),
            (1, 3, 4, 1, 2, 3, 2, 4),
            (3, 2, 1, 4, 3, 1, 4, 2),
            (2, 4, 2, 3, 1, 4, 2, 1),
            (4, 1, 2, 2, 3, 2, 1, 3),
        )
        RIGHT_MONITOR_SERIES = (
            (2, 1, 3, 1, 4, 2, 1, 3),
            (1, 3, 2, 4, 2, 1, 3, 2),
            (3, 2, 4, 1, 3, 2, 4, 1),
            (4, 1, 2, 3, 1, 4, 2, 3),
            (2, 4, 1, 2, 3, 1, 4, 2),
            (1, 2, 3, 4, 2, 3, 1, 4),
        )
        SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        RESPONSE_STREAM_SECONDS_PER_CHAR = 0.012
        COMMAND_CHOICES = (
            ("/home", "open the Jarvis-Agent home page"),
            ("/model", "choose the active MLX model"),
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

        CSS = """
        Screen {
            background: transparent;
            color: #e6e8eb;
            layers: base popup composer;
        }

        Screen > .screen--selection {
            background: #ffe45c;
            color: #101216;
            text-style: bold;
        }

        #workspace {
            height: 1fr;
            padding: 1 2 6 2;
        }

        #topbar {
            height: 1;
            color: #8d93a1;
            text-style: bold;
        }

        #git-status-info {
            width: auto;
            color: #7d8492;
        }

        #repo-path-info {
            width: 1fr;
            color: #7d8492;
        }

        #repo-path-info:hover {
            background: #273349;
            color: #e6e8eb;
            text-style: bold;
        }

        #context-info {
            width: auto;
            min-width: 17;
            margin-left: 2;
            color: #ffe45c;
            content-align: right middle;
        }

        #todo-info {
            width: auto;
            min-width: 7;
            margin-left: 2;
            color: #c8d0da;
            content-align: right middle;
        }

        #todo-panel {
            height: auto;
            margin-top: 1;
            padding: 1 2;
            border: round #303745;
            background: transparent;
            color: #c8d0da;
        }

        #turn-history {
            height: auto;
            max-height: 7;
            margin-top: 1;
            margin-bottom: 1;
            border: round #303745;
            background: transparent;
            color: #e6e8eb;
            border-title-align: left;
            border-title-color: #b897ff;
            border-title-background: transparent;
        }

        #turn-history ListItem {
            height: 1;
            padding: 0 2;
        }

        #turn-history ListItem.--highlight {
            background: #273349;
            color: #ffffff;
        }

        #turn-history ListItem:hover {
            background: #273349;
            color: #ffffff;
        }

        #hero {
            height: auto;
            min-height: 20;
            padding: 1 2;
            margin-top: 3;
            margin-bottom: 1;
            border: round #4f7cff;
            background: transparent;
            color: #f5f7fb;
        }

        #logo-monitor {
            width: 16;
            height: 8;
            padding: 0 0;
            content-align: left top;
            color: #ffffff;
        }

        #home-panel {
            width: 1fr;
            padding: 0 2 1 2;
        }

        #log {
            height: 1fr;
            padding: 1 3;
            border: round #303745;
            background: transparent;
            scrollbar-size-horizontal: 0;
            border-subtitle-align: right;
            border-subtitle-color: #8d93a1;
            border-subtitle-background: transparent;
        }

        #thinking {
            height: 1;
            margin: 0 2 3 2;
            color: #aee4fc;
            dock: bottom;
            layer: popup;
            overlay: screen;
        }

        #output-metrics {
            width: auto;
            height: 1;
            margin: 0 5 6 2;
            color: #8d93a1;
            background: transparent;
            dock: bottom;
            layer: popup;
            overlay: screen;
            content-align: right middle;
        }

        #suggestions {
            height: auto;
            max-height: 8;
            margin: 0 2 4 2;
            border: tall #303745;
            background: transparent;
            dock: bottom;
            layer: popup;
            overlay: screen;
            constrain: none inside;
        }

        #suggestions ListItem {
            height: 1;
            padding: 0 2;
        }

        #suggestions ListItem.--highlight {
            background: #273349;
            color: #ffffff;
        }

        #prompt {
            width: 1fr;
            height: 1;
            margin: 0;
            padding: 0 0;
            border: none;
            background: transparent;
        }

        #prompt-icon {
            width: 3;
            height: 1;
            color: #d7b7ff;
            text-style: bold;
            content-align: center middle;
        }

        #prompt-row {
            height: 1;
            padding: 0 1;
        }

        #composer {
            width: 100%;
            height: 3;
            margin: 0 2 0 2;
            padding: 0 0;
            border: round #6d5cae;
            background: transparent;
            dock: bottom;
            layer: composer;
            overlay: screen;
            border-subtitle-align: right;
            border-subtitle-color: #8d93a1;
            border-subtitle-background: transparent;
        }
        """

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
            self.responding_started_at: float | None = None
            self.response_text = ""
            self.response_index = 0
            self.response_should_continue = True
            self.response_last_tick = 0.0
            self.output_raw_text = ""
            self.output_column = 0
            self.output_render_width = 0
            self.spinner_index = 0
            self.last_copied_selection = ""
            self.copy_notice_until = 0.0
            self.suggestion_mode: str | None = None
            self.suggestion_values: list[str] = []
            self.todo_panel_open = False
            self.todo_items: list[str] = []
            self.turn_records: list[TurnRecord] = []
            self.current_turn_index: int | None = None
            self.history_mode = "turns"
            self.history_expanded = False
            self.history_pinned = False
            self.pending_history_digit = ""
            self.session_choices: list[str] = []
            self.output_metrics_text = ""
            self.output_metrics_detail = ""

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
                Log(id="log", highlight=False),
                id="workspace",
            )
            yield Static("", id="thinking")
            yield Static("", id="output-metrics")
            yield ListView(id="suggestions")
            yield Vertical(
                Horizontal(
                    Static("❱", id="prompt-icon"),
                    Input(placeholder="Ask Jarvis-Agent, or use /help, /home, /model, /resume, /index ...", id="prompt"),
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
            self.query_one("#prompt", Input).focus()
            self.hide_suggestions()
            self.set_interval(0.12, self.animate_home)
            self.set_interval(0.10, self.update_thinking_status)
            self.set_interval(0.03, self.update_response_stream)
            self.set_interval(0.20, self.auto_copy_selection)
            self.hide_thinking_status()
            self.clear_output_metrics_caption()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            raw = event.value.strip()
            event.input.value = ""
            if not raw:
                return
            self.hide_suggestions()
            self.process_raw(raw)

        def process_raw(self, raw: str) -> None:
            log = self.query_one("#log", Log)

            if raw == "/home":
                self.show_home()
                return

            self.hide_home()
            self.set_chat_visible(True)

            if raw == "/clear":
                log.clear()
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

        async def on_input_changed(self, event: Input.Changed) -> None:
            await self.refresh_suggestions(event.value)

        def on_click(self, event) -> None:
            widget = getattr(event, "widget", None)
            widget_id = getattr(widget, "id", None)
            if widget_id == "repo-path-info":
                event.stop()
                self.copy_project_path()
                return
            if widget_id == "todo-info":
                event.stop()
                self.toggle_todo_panel()

        def on_resize(self) -> None:
            self.enforce_output_scrollbars()
            self.reflow_output()
            self.update_repo_path_info()

        async def on_key(self, event) -> None:
            if self.history_expanded and event.key == "escape":
                event.prevent_default()
                event.stop()
                self.collapse_history()
                self.query_one("#prompt", Input).focus()
                return
            if self.thinking_started_at is not None:
                return
            prompt_input = self.query_one("#prompt", Input)
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
            if self.suggestion_mode == "models" and event.character and event.character.isdigit():
                index = int(event.character) - 1
                if 0 <= index < len(self.suggestion_values):
                    event.prevent_default()
                    event.stop()
                    await self.choose_model_suggestion(index)
                    return
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

        async def on_list_view_selected(self, event: ListView.Selected) -> None:
            if event.list_view.id == "turn-history":
                event.stop()
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

        async def refresh_suggestions(self, value: str) -> None:
            stripped = value.strip()
            if not stripped.startswith("/"):
                self.hide_suggestions()
                return
            if stripped == "/model" or stripped.startswith("/model "):
                selector = stripped.removeprefix("/model").strip()
                if selector and not selector.isdigit():
                    self.hide_suggestions()
                    return
                initial_index = int(selector) - 1 if selector.isdigit() else 0
                await self.show_model_suggestions(initial_index=initial_index)
                return
            if " " in stripped:
                self.hide_suggestions()
                return
            matches = [(command, description) for command, description in self.COMMAND_CHOICES if command.startswith(stripped)]
            if not matches:
                self.hide_suggestions()
                return
            labels = [self.render_command_suggestion(command, description) for command, description in matches]
            await self.set_suggestions("commands", [command for command, _ in matches], labels)

        async def show_model_suggestions(self, initial_index: int = 0) -> None:
            labels = [self.render_model_suggestion(index, model) for index, model in enumerate(AVAILABLE_MODELS, start=1)]
            await self.set_suggestions("models", list(AVAILABLE_MODELS), labels, initial_index=initial_index)

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
            suggestions = self.query_one("#suggestions", ListView)
            suggestions.styles.display = "none"
            suggestions.styles.offset = (0, 0)

        def position_suggestions(self, value_count: int) -> None:
            suggestions = self.query_one("#suggestions", ListView)
            suggestions.styles.offset = (0, 0)

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
            prompt_input = self.query_one("#prompt", Input)
            if command == "/model":
                self.set_prompt_value(prompt_input, "/model ")
                prompt_input.focus()
                await self.show_model_suggestions()
                return
            if not submit:
                value = f"{command} " if command in self.ARG_COMMANDS else command
                self.set_prompt_value(prompt_input, value)
                prompt_input.focus()
                self.hide_suggestions()
                return
            self.hide_suggestions()
            prompt_input.value = ""
            self.process_raw(command)

        async def choose_model_suggestion(self, index: int) -> None:
            model_number = index + 1
            self.hide_suggestions()
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.value = ""
            self.process_raw(f"/model {model_number}")

        def set_prompt_value(self, prompt_input: Input, value: str) -> None:
            prompt_input.value = value
            prompt_input.cursor_position = len(value)

        def render_command_suggestion(self, command: str, description: str) -> str:
            return f"[#aee4fc]{command:<10}[/] [#8d93a1]{_escape_markup(description)}[/]"

        def render_model_suggestion(self, index: int, model: str) -> str:
            marker = "current" if model == self.ui.config.model.model else "available"
            return f"[#ffe45c]{index}[/]  {_escape_markup(compact_model_name(model, max_chars=64))}  [#8d93a1]{marker}[/]"

        def action_clear_log(self) -> None:
            self.query_one("#log", Log).clear()
            self.clear_output_metrics_caption()
            self.reset_output_buffer()

        def action_toggle_history(self) -> None:
            self.history_pinned = not self.history_pinned
            self.history_expanded = self.history_pinned
            self.refresh_history_panel_later()

        def collapse_history(self) -> None:
            self.history_pinned = False
            self.history_expanded = False
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
            self.turn_records.append(TurnRecord(prompt=raw, timestamp=timestamp, created_at=time.time()))
            self.current_turn_index = len(self.turn_records) - 1
            self.history_mode = "turns"
            self.reset_output_box(raw, timestamp)
            self.refresh_history_panel_later()

        def reset_output_box(self, raw: str, timestamp: str) -> None:
            log = self.query_one("#log", Log)
            log.clear()
            log.border_title = f" {raw} "
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
                    visible_records = [visible_records[-1]]
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
            return self.history_item(self.render_history_record(index, record), tooltip=_exact_time_label(record.created_at))

        def render_history_record(self, index: int, record: TurnRecord) -> str:
            relative = _relative_time_label(record.created_at)
            width = self.history_label_width()
            prefix = f"{index}  "
            max_prompt_chars = max(8, width - cell_len(prefix) - cell_len(relative) - 2)
            prompt = _single_line(record.prompt, max_chars=max_prompt_chars)
            left = f"[#8d93a1]{index}[/]  {_escape_markup(prompt)}"
            plain_left = f"{prefix}{prompt}"
            spacing = max(1, width - cell_len(plain_left) - cell_len(relative))
            return f"{left}{' ' * spacing}[#6f7785]{relative}[/]"

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
            self.show_output_snapshot(record.prompt, record.output or "(no output yet)", record.metrics, record.metrics_detail)

        def show_output_snapshot(self, title: str, output: str, metrics: str = "", metrics_detail: str = "") -> None:
            self.set_chat_visible(True)
            log = self.query_one("#log", Log)
            log.clear()
            log.border_title = f" {title} "
            log.border_subtitle = ""
            self.update_output_metrics_caption(metrics, metrics_detail)
            self.output_raw_text = output.rstrip() + "\n\n"
            self.output_render_width = self.output_wrap_width()
            wrapped, column = wrap_output_text(self.output_raw_text, self.output_render_width)
            log.write(wrapped)
            self.output_column = column
            self.update_topbar_status()

        def is_llm_request(self, raw: str) -> bool:
            return bool(raw and (not raw.startswith("/") or raw.startswith("/ask ")))

        def is_generation_active(self) -> bool:
            return self.thinking_started_at is not None or self.responding_started_at is not None

        def start_llm_request(self, raw: str) -> None:
            prompt = raw.removeprefix("/ask ").strip() if raw.startswith("/ask ") else raw
            self.thinking_started_at = time.monotonic()
            self.responding_started_at = None
            self.thinking_prompt = prompt
            self.thinking_context_tokens = estimate_context_tokens(prompt)
            self.spinner_index = 0
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.disabled = True
            self.update_thinking_status()
            threading.Thread(target=self.run_llm_request, args=(raw,), daemon=True).start()

        def run_llm_request(self, raw: str) -> None:
            try:
                response = self.ui.dispatch(raw)
                self.call_from_thread(self.finish_llm_request, response, None)
            except Exception as exc:
                self.call_from_thread(self.finish_llm_request, None, exc)

        def finish_llm_request(self, response: TUIResponse | None, exc: Exception | None) -> None:
            self.thinking_started_at = None
            self.thinking_prompt = ""
            self.thinking_context_tokens = 0
            if exc is not None:
                self.write_output(f"ERROR: {exc}")
                self.finish_response_stream()
            elif response is not None and response.output:
                self.sync_config_from_ui()
                self.start_response_stream(response.output, response.should_continue)
                return
            else:
                self.finish_response_stream()

        def update_thinking_status(self) -> None:
            if self.responding_started_at is not None:
                elapsed = time.monotonic() - self.responding_started_at
                current_tokens = estimate_context_tokens(self.response_text[: self.response_index])
                total_tokens = estimate_context_tokens(self.response_text)
                tokens_per_second = current_tokens / elapsed if elapsed > 0 else 0.0
                self.query_one("#thinking", Static).update(
                    f"↳ Responding... {elapsed:.1f}s | ~{current_tokens}/{total_tokens} tokens | {tokens_per_second:.1f} tokens/sec"
                )
                return
            if self.thinking_started_at is None:
                if self.copy_notice_until and time.monotonic() > self.copy_notice_until:
                    self.copy_notice_until = 0.0
                    self.hide_thinking_status()
                return
            elapsed = time.monotonic() - self.thinking_started_at
            frame = self.SPINNER_FRAMES[self.spinner_index % len(self.SPINNER_FRAMES)]
            self.spinner_index += 1
            self.query_one("#thinking", Static).update(
                f"{frame} Thinking... {elapsed:.1f}s | context ~{self.thinking_context_tokens} tokens | max gen {self.ui.config.model.max_tokens}"
            )

        def hide_thinking_status(self) -> None:
            self.query_one("#thinking", Static).update("")

        def write_output(self, output: str) -> None:
            body, metrics, metrics_detail = split_output_metrics_detail(output)
            if metrics:
                self.set_output_metrics(metrics, metrics_detail)
            self.write_wrapped_output(body.rstrip() + "\n\n")

        def start_response_stream(self, output: str, should_continue: bool) -> None:
            body, metrics, metrics_detail = split_output_metrics_detail(output)
            if metrics:
                self.set_output_metrics(metrics, metrics_detail)
            self.response_text = body.rstrip() + "\n\n"
            self.response_index = 0
            self.response_should_continue = should_continue
            self.responding_started_at = time.monotonic()
            self.response_last_tick = self.responding_started_at
            self.update_response_stream()

        def set_output_metrics(self, metrics: str, metrics_detail: str = "") -> None:
            self.query_one("#log", Log).border_subtitle = ""
            self.update_output_metrics_caption(metrics, metrics_detail)
            if self.current_turn_index is None:
                return
            if not 0 <= self.current_turn_index < len(self.turn_records):
                return
            self.turn_records[self.current_turn_index].metrics = metrics
            self.turn_records[self.current_turn_index].metrics_detail = metrics_detail

        def update_output_metrics_caption(self, metrics: str, metrics_detail: str = "") -> None:
            self.output_metrics_text = metrics
            self.output_metrics_detail = metrics_detail
            caption = self.query_one("#output-metrics", Static)
            caption.update(f" {metrics} " if metrics else "")
            caption.tooltip = metrics_detail or None
            self.refresh_output_metrics_visibility()

        def clear_output_metrics_caption(self) -> None:
            self.update_output_metrics_caption("", "")

        def refresh_output_metrics_visibility(self) -> None:
            caption = self.query_one("#output-metrics", Static)
            log_visible = self.query_one("#log", Log).styles.display != "none"
            caption.styles.display = "block" if log_visible and self.output_metrics_text else "none"

        def update_response_stream(self) -> None:
            if self.responding_started_at is None or not self.response_text:
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
            self.write_wrapped_output(chunk)
            if self.response_index >= len(self.response_text):
                self.finish_response_stream()

        def write_wrapped_output(self, text: str) -> None:
            if not text:
                return
            self.output_raw_text += text
            wrap_width = self.output_wrap_width()
            if wrap_width != self.output_render_width:
                self.reflow_output(wrap_width)
                return
            pieces: list[str] = []
            for character in text:
                if character == "\r":
                    continue
                if character == "\n":
                    pieces.append(character)
                    self.output_column = 0
                    continue
                character_width = max(1, cell_len(character))
                if self.output_column and self.output_column + character_width > wrap_width:
                    pieces.append("\n")
                    self.output_column = 0
                pieces.append(character)
                self.output_column += character_width
            self.query_one("#log", Log).write("".join(pieces))
            self.update_current_turn_output()
            self.update_topbar_status()

        def output_wrap_width(self) -> int:
            log = self.query_one("#log", Log)
            width = log.content_size.width or log.size.width or 80
            return max(24, width - 2)

        def reflow_output(self, wrap_width: int | None = None) -> None:
            if not self.output_raw_text:
                return
            width = wrap_width or self.output_wrap_width()
            self.output_render_width = width
            wrapped, column = wrap_output_text(self.output_raw_text, width)
            log = self.query_one("#log", Log)
            log.clear()
            log.show_horizontal_scrollbar = False
            log.write(wrapped)
            self.output_column = column
            self.update_current_turn_output()
            self.update_topbar_status()

        def reset_output_buffer(self) -> None:
            self.output_raw_text = ""
            self.output_column = 0
            self.output_render_width = self.output_wrap_width()

        def enforce_output_scrollbars(self) -> None:
            log = self.query_one("#log", Log)
            log.show_horizontal_scrollbar = False
            log.styles.scrollbar_size_horizontal = 0

        def finish_response_stream(self) -> None:
            should_continue = self.response_should_continue
            self.responding_started_at = None
            self.response_text = ""
            self.response_index = 0
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.disabled = False
            prompt_input.focus()
            self.hide_thinking_status()
            if not should_continue:
                self.exit()

        def update_turn_panel(self, raw: str) -> None:
            if self.current_turn_index is not None and 0 <= self.current_turn_index < len(self.turn_records):
                self.turn_records[self.current_turn_index].prompt = raw
                self.refresh_history_panel_later()

        def render_turn_panel(self, raw: str | None = None) -> str:
            if not raw:
                return "[#8d93a1]❱ Ready[/]"
            return f"[#8d93a1]❱[/] {_escape_markup(raw)} [#8d93a1]{current_time_label()}[/]"

        def render_topbar(self) -> str:
            return self.render_repo_info()

        def render_repo_info(self) -> str:
            return f"{self.render_git_status_info()} {self.render_repo_path_info()}".strip()

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

        def render_context_info(self) -> str:
            return f"{_format_token_count(self.current_context_tokens())} / {_format_token_count(self.CONTEXT_LIMIT_TOKENS)}"

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
            text = "\n".join(part for part in (self.output_raw_text, self.thinking_prompt, self.response_text) if part)
            return estimate_context_tokens(text)

        def update_topbar_status(self) -> None:
            tokens = self.current_context_tokens()
            percent = (tokens / self.CONTEXT_LIMIT_TOKENS) * 100
            context_info = self.query_one("#context-info", Static)
            context_info.update(self.render_context_info())
            context_info.tooltip = f"Context usage: {tokens:,} / {self.CONTEXT_LIMIT_TOKENS:,} tokens ({percent:.1f}%)"

            todo_info = self.query_one("#todo-info", Static)
            todo_info.update(self.render_todo_info())
            todo_info.tooltip = "Click to show the Jarvis-Agent to-do list."

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
            self.query_one("#log", Log).styles.display = display
            self.query_one("#thinking", Static).styles.display = display
            self.refresh_output_metrics_visibility()

        def animate_home(self) -> None:
            if not self.home_visible:
                return
            max_frame = self.SPLASH_REVEAL_FRAMES + self.SPLASH_MONITOR_FRAMES
            self.splash_frame = min(self.splash_frame + 1, max_frame)
            self.update_logo_monitor()

        def update_logo_monitor(self) -> None:
            self.query_one("#logo-monitor", Static).update(self.render_logo_monitor_frame())

        def render_logo_monitor_frame(self) -> str:
            reveal_row = min(self.splash_frame, self.HISTOGRAM_ROWS - 1)
            final_phase = self.splash_frame >= self.SPLASH_REVEAL_FRAMES + self.SPLASH_MONITOR_FRAMES
            rows: list[str] = []
            for y in range(self.HISTOGRAM_ROWS):
                cells: list[str] = []
                for x in range(self.HISTOGRAM_ROWS):
                    color = self.logo_cell_color(x, y, reveal_row, final_phase)
                    cells.append(f"[{color}]⬤[/]")
                rows.append(" ".join(cells))
            return "\n".join(rows)

        def logo_cell_color(self, x: int, y: int, reveal_row: int, final_phase: bool) -> str:
            left_background = "#2f7fd8"
            left_active = "#ffffff"
            right_background = "#134a8d"
            right_active = "#f6d33f"
            inactive = "#303745"

            if y > reveal_row:
                return inactive

            if final_phase:
                cell = self.ui.branding.logo_pattern[y][x]
                if x < self.HISTOGRAM_COLS:
                    return left_active if cell == "W" else left_background
                return right_active if cell == "Y" else right_background

            if x < self.HISTOGRAM_COLS:
                widths = self.current_monitor_widths("left")
                active = x >= self.HISTOGRAM_COLS - widths[y]
                return left_active if active else left_background
            widths = self.current_monitor_widths("right")
            active = x - self.HISTOGRAM_COLS < widths[y]
            return right_active if active else right_background

        def current_monitor_widths(self, side: str) -> tuple[int, ...]:
            series = self.LEFT_MONITOR_SERIES if side == "left" else self.RIGHT_MONITOR_SERIES
            index = max(0, self.splash_frame - self.SPLASH_REVEAL_FRAMES)
            if index >= self.SPLASH_MONITOR_FRAMES - 6:
                return self.final_logo_widths(side)
            return series[index % len(series)]

        def final_logo_widths(self, side: str) -> tuple[int, ...]:
            return self.ui.branding.logo_widths(side)

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

    JarvisAgentApp(config).run()
    return 0


def _escape_markup(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def get_git_info(project_root: Path) -> GitInfo:
    branch = _run_git(project_root, "branch", "--show-current")
    if not branch:
        branch = _run_git(project_root, "rev-parse", "--short", "HEAD")

    git_dir = _run_git(project_root, "rev-parse", "--git-dir")
    common_dir = _run_git(project_root, "rev-parse", "--git-common-dir")
    is_worktree = False
    if git_dir and common_dir:
        git_dir_path = _resolve_git_path(project_root, git_dir)
        common_dir_path = _resolve_git_path(project_root, common_dir)
        is_worktree = git_dir_path != common_dir_path

    main_worktree = _main_worktree_path(project_root) if is_worktree else None
    return GitInfo(branch=branch, is_worktree=is_worktree, main_worktree=main_worktree)


def _run_git(project_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_git_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _main_worktree_path(project_root: Path) -> Path | None:
    output = _run_git(project_root, "worktree", "list", "--porcelain")
    if not output:
        return None
    for block in output.split("\n\n"):
        first_line = block.splitlines()[0] if block.splitlines() else ""
        if not first_line.startswith("worktree "):
            continue
        candidate = Path(first_line.removeprefix("worktree ")).expanduser().resolve()
        if candidate != project_root.resolve():
            return candidate
    return None


def _home_relative_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        return str(resolved)
    return "~" if not relative.parts else f"~/{relative}"


def _format_token_count(tokens: int) -> str:
    if tokens >= 1_000:
        return f"{round(tokens / 1_000):.0f}K"
    return str(tokens)


def _single_line(text: str, max_chars: int) -> str:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars - 1]}…"


METRICS_RE = re.compile(r"\n*\[metrics\]\s*(?P<metrics>.*)\s*$", re.DOTALL)


def split_output_metrics(output: str) -> tuple[str, str]:
    body, metrics, _ = split_output_metrics_detail(output)
    return body, metrics


def split_output_metrics_detail(output: str) -> tuple[str, str, str]:
    stripped = output.rstrip()
    match = METRICS_RE.search(stripped)
    if not match:
        return output, "", ""
    body = stripped[: match.start()].rstrip()
    metrics_detail = " ".join(match.group("metrics").split())
    return body, compact_metrics(metrics_detail), metrics_detail


def compact_metrics(metrics: str) -> str:
    def match_value(pattern: str) -> str:
        match = re.search(pattern, metrics)
        return match.group(1) if match else ""

    prompt = match_value(r"prompt:\s*(\d+)\s*tokens")
    generation = match_value(r"generation:\s*(\d+)\s*tokens")
    context = match_value(r"context:\s*(\d+)\s*tokens")
    memory = match_value(r"peak memory:\s*([0-9.]+)\s*GB")
    parts: list[str] = []
    if prompt:
        parts.append(f"prompt {prompt} tok")
    if generation:
        parts.append(f"gen {generation} tok")
    if context:
        parts.append(f"ctx {context} tok")
    if memory:
        parts.append(f"mem {memory} GB")
    return " · ".join(parts) if parts else metrics


def _relative_time_label(created_at: float) -> str:
    elapsed = max(0, int(time.time() - created_at))
    if elapsed < 60:
        return "now"
    minutes = elapsed // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr"
    return f"{hours // 24} d"


def _exact_time_label(created_at: float) -> str:
    return datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S")


def estimate_context_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, round(len(stripped) / 4))


def wrap_output_text(text: str, width: int) -> tuple[str, int]:
    pieces: list[str] = []
    column = 0
    for character in text:
        if character == "\r":
            continue
        if character == "\n":
            pieces.append(character)
            column = 0
            continue
        character_width = max(1, cell_len(character))
        if column and column + character_width > width:
            pieces.append("\n")
            column = 0
        pieces.append(character)
        column += character_width
    return "".join(pieces), column


def current_time_label() -> str:
    return datetime.now().strftime("%-I:%M %p")


def _compact_path(path: str, max_chars: int = 56) -> str:
    if len(path) <= max_chars:
        return path
    return f"...{path[-max_chars + 3:]}"


def _compact_middle_path(path: str, max_chars: int = 56) -> str:
    if len(path) <= max_chars:
        return path
    if max_chars <= 6:
        return path[: max(0, max_chars - 3)] + "..."
    head = max(3, int(max_chars * 0.65))
    tail = max_chars - head - 3
    if tail <= 0:
        return f"{path[: max_chars - 3]}..."
    return f"{path[:head]}...{path[-tail:]}"


def _compact_model_name(model: str, max_chars: int = 42) -> str:
    return compact_model_name(model, max_chars=max_chars)
