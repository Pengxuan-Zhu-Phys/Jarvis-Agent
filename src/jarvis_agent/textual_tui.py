from __future__ import annotations

from datetime import datetime
import threading
import time

from rich.cells import cell_len

from jarvis_agent.branding import TEXT_GRADIENT_COLORS
from jarvis_agent.config import AVAILABLE_MODELS, AgentConfig
from jarvis_agent.tui import TUIResponse, TerminalUI


class TextualUnavailable(RuntimeError):
    """Raised when the optional Textual dependency is not installed."""


def run_textual_ui(config: AgentConfig) -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Input, ListItem, ListView, Log, Static
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TextualUnavailable("Textual is not installed. Install with: pip install -e '.[tui]'") from exc

    class JarvisAgentApp(App[None]):
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
        }

        Screen > .screen--selection {
            background: #ffe45c;
            color: #101216;
            text-style: bold;
        }

        #workspace {
            height: 1fr;
            padding: 1 2;
        }

        #topbar {
            height: 1;
            color: #8d93a1;
            text-style: bold;
        }

        #turn {
            height: auto;
            min-height: 3;
            margin-top: 1;
            margin-bottom: 1;
            padding: 1 2;
            border: tall #303745;
            color: #e6e8eb;
        }

        #hero {
            height: auto;
            min-height: 20;
            padding: 1 2;
            margin-bottom: 1;
            border: heavy #4f7cff;
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
            border: tall #303745;
            background: transparent;
            scrollbar-size-horizontal: 0;
        }

        #thinking {
            height: 1;
            margin-top: 1;
            color: #aee4fc;
        }

        #suggestions {
            height: auto;
            max-height: 8;
            margin-top: 1;
            border: tall #303745;
            background: transparent;
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
            margin-top: 1;
            border: tall #4f7cff;
        }

        #model-info {
            height: 1;
            color: #8d93a1;
            content-align: right middle;
        }
        """

        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("ctrl+l", "clear_log", "Clear"),
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

        def compose(self) -> ComposeResult:
            yield Vertical(
                Static(self.render_topbar(), id="topbar"),
                Static(self.render_turn_panel(), id="turn"),
                Horizontal(
                    Static(self.render_logo_monitor_frame(), id="logo-monitor"),
                    Static(self.render_home_panel(), id="home-panel"),
                    id="hero",
                ),
                Log(id="log", highlight=False),
                Static("", id="thinking"),
                ListView(id="suggestions"),
                Input(placeholder="Ask Jarvis-Agent, or use /help, /home, /model, /resume, /index ...", id="prompt"),
                Static(self.render_model_info(), id="model-info"),
                id="workspace",
            )

        def on_mount(self) -> None:
            self.title = "Jarvis-Agent"
            self.sub_title = self.agent_config.project.name
            self.enforce_output_scrollbars()
            self.query_one("#prompt", Input).focus()
            self.hide_suggestions()
            self.set_interval(0.12, self.animate_home)
            self.set_interval(0.10, self.update_thinking_status)
            self.set_interval(0.03, self.update_response_stream)
            self.set_interval(0.20, self.auto_copy_selection)
            self.hide_thinking_status()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            raw = event.value.strip()
            event.input.value = ""
            if not raw:
                return
            self.hide_suggestions()
            self.process_raw(raw)

        def process_raw(self, raw: str) -> None:
            self.update_turn_panel(raw)
            log = self.query_one("#log", Log)

            if raw == "/clear":
                log.clear()
                self.reset_output_buffer()
                return

            if raw == "/home":
                self.show_home()
                return

            self.hide_home()

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

        async def on_input_changed(self, event: Input.Changed) -> None:
            await self.refresh_suggestions(event.value)

        def on_resize(self) -> None:
            self.enforce_output_scrollbars()
            self.reflow_output()

        async def on_key(self, event) -> None:
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

        async def on_list_view_selected(self, event: ListView.Selected) -> None:
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

        def hide_suggestions(self) -> None:
            self.suggestion_mode = None
            self.suggestion_values = []
            self.query_one("#suggestions", ListView).styles.display = "none"

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
                prompt_input.value = "/model "
                prompt_input.focus()
                await self.show_model_suggestions()
                return
            if not submit:
                prompt_input.value = f"{command} " if command in self.ARG_COMMANDS else command
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

        def render_command_suggestion(self, command: str, description: str) -> str:
            return f"[#aee4fc]{command:<10}[/] [#8d93a1]{_escape_markup(description)}[/]"

        def render_model_suggestion(self, index: int, model: str) -> str:
            marker = "current" if model == self.ui.config.model.model else "available"
            return f"[#ffe45c]{index}[/]  {_escape_markup(_compact_model_name(model, max_chars=64))}  [#8d93a1]{marker}[/]"

        def action_clear_log(self) -> None:
            self.query_one("#log", Log).clear()
            self.reset_output_buffer()

        def copy_to_clipboard(self, text: str) -> None:
            super().copy_to_clipboard(text)
            self.copy_notice_until = time.monotonic() + 1.5
            if self.thinking_started_at is None:
                self.query_one("#thinking", Static).update("✓ Copied selection")

        def auto_copy_selection(self) -> None:
            selection = self.screen.get_selected_text()
            if not selection:
                self.last_copied_selection = ""
                return
            if selection == self.last_copied_selection:
                return
            self.last_copied_selection = selection
            self.copy_to_clipboard(selection)

        def is_llm_request(self, raw: str) -> bool:
            return bool(raw and (not raw.startswith("/") or raw.startswith("/ask ")))

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
            self.write_wrapped_output(output.rstrip() + "\n\n")

        def start_response_stream(self, output: str, should_continue: bool) -> None:
            self.response_text = output.rstrip() + "\n\n"
            self.response_index = 0
            self.response_should_continue = should_continue
            self.responding_started_at = time.monotonic()
            self.response_last_tick = self.responding_started_at
            self.update_response_stream()

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
            self.query_one("#turn", Static).update(self.render_turn_panel(raw))

        def render_turn_panel(self, raw: str | None = None) -> str:
            if not raw:
                return "[#8d93a1]› Ready[/]"
            return f"[#8d93a1]›[/] {_escape_markup(raw)} [#8d93a1]{current_time_label()}[/]"

        def render_topbar(self) -> str:
            root = _compact_path(str(self.ui.config.project.root))
            model = _compact_model_name(self.ui.config.model.model)
            return f"✧ jarvis-agent [#b897ff]{self.ui.config.project.name}[/] {root} | {model}"

        def render_model_info(self) -> str:
            model = _compact_model_name(self.ui.config.model.model)
            return (
                f"{self.ui.config.model.backend}:{model} "
                f"· max gen {self.ui.config.model.max_tokens} "
                f"· temp {self.ui.config.model.temperature}"
            )

        def sync_config_from_ui(self) -> None:
            self.agent_config = self.ui.config
            self.query_one("#topbar", Static).update(self.render_topbar())
            self.query_one("#model-info", Static).update(self.render_model_info())
            self.query_one("#home-panel", Static).update(self.render_home_panel())

        def show_home(self) -> None:
            self.splash_frame = 0
            self.home_visible = True
            hero = self.query_one("#hero", Horizontal)
            hero.styles.display = "block"
            self.query_one("#home-panel", Static).update(self.render_home_panel())
            self.update_logo_monitor()

        def hide_home(self) -> None:
            self.home_visible = False
            self.query_one("#hero", Horizontal).styles.display = "none"

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


def _compact_model_name(model: str, max_chars: int = 42) -> str:
    tail = model.rsplit("/", 1)[-1]
    if len(tail) <= max_chars:
        return tail
    return f"{tail[:max_chars - 1]}…"
