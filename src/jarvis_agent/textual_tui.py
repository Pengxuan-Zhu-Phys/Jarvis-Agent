from __future__ import annotations

from jarvis_agent.config import AgentConfig
from jarvis_agent.tui import TerminalUI


class TextualUnavailable(RuntimeError):
    """Raised when the optional Textual dependency is not installed."""


def run_textual_ui(config: AgentConfig) -> int:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Vertical
        from textual.widgets import Footer, Header, Input, RichLog, Static
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TextualUnavailable("Textual is not installed. Install with: pip install -e '.[tui]'") from exc

    class JarvisAgentApp(App[None]):
        CSS = """
        Screen {
            background: #101216;
            color: #e6e8eb;
        }

        #workspace {
            height: 1fr;
            padding: 1 2;
        }

        #hero {
            height: auto;
            min-height: 14;
            padding: 1 2;
            margin-bottom: 1;
            border: heavy #4f7cff;
            background: #151923;
            color: #f5f7fb;
        }

        #log {
            height: 1fr;
            padding: 1 2;
            border: tall #303745;
            background: #0c0e12;
        }

        #prompt {
            margin-top: 1;
            border: tall #4f7cff;
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

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Vertical(
                Static(self.ui.startup_page(), id="hero"),
                RichLog(id="log", wrap=True, highlight=True, markup=False),
                Input(placeholder="Ask Jarvis-Agent, or use /help, /index, /yaml, /explain ...", id="prompt"),
                id="workspace",
            )
            yield Footer()

        def on_mount(self) -> None:
            self.title = "Jarvis-Agent"
            self.sub_title = self.agent_config.project.name
            self.query_one("#prompt", Input).focus()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            raw = event.value.strip()
            event.input.value = ""
            if not raw:
                return

            log = self.query_one("#log", RichLog)
            log.write(f"> {raw}")
            try:
                response = self.ui.dispatch(raw)
            except Exception as exc:
                log.write(f"ERROR: {exc}")
                return

            if raw == "/clear":
                log.clear()
                self.query_one("#hero", Static).update(self.ui.startup_page())
                return

            if response.output:
                log.write(response.output)
            if not response.should_continue:
                self.exit()

        def action_clear_log(self) -> None:
            self.query_one("#log", RichLog).clear()
            self.query_one("#hero", Static).update(self.ui.startup_page())

    JarvisAgentApp(config).run()
    return 0

