from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from jarvis_agent.config import AgentConfig
from jarvis_agent.workflows import WorkflowEngine


HELP = """Commands:
  /help             show this help
  /status           show project and model status
  /index            index the configured project
  /explain PATH     build an explanation prompt for a file
  /yaml PATH        run a lightweight YAML review
  /ask PROMPT       send a prompt to the configured model
  /clear            redraw the startup page
  /quit             exit

Plain text without a leading slash is sent to the configured model.
"""


@dataclass(frozen=True)
class TUIResponse:
    should_continue: bool = True
    output: str = ""


class TerminalUI:
    def __init__(self, config: AgentConfig, engine: WorkflowEngine | None = None) -> None:
        self.config = config
        self.engine = engine or WorkflowEngine(config)

    def run(self) -> int:
        print(self.startup_page())
        while True:
            try:
                raw = input("jarvis-agent / ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not raw:
                continue
            try:
                response = self.dispatch(raw)
            except Exception as exc:
                print(f"ERROR: {exc}")
                continue
            if response.output:
                print(response.output)
            if not response.should_continue:
                return 0

    def startup_page(self) -> str:
        title = "Jarvis-Agent Build"
        width = 78
        rule = "=" * width
        return "\n".join(
            [
                rule,
                title.center(width),
                rule,
                "Local HEP assistant for package understanding, YAML configuration,",
                "workflow automation, and MLX-backed Qwen3-Coder experiments.",
                "",
                f"Project : {self.config.project.root}",
                f"Model   : {self.config.model.backend}:{self.config.model.model}",
                "",
                "Start here:",
                "  /index                 scan the current HEP package",
                "  /yaml path.yaml         review a YAML configuration",
                "  /explain path/to/file   build a package-aware explanation prompt",
                "  /ask question           ask the local model",
                "",
                "Use /help for all commands. Use /quit to exit.",
                rule,
            ]
        )

    def handle(self, raw: str) -> bool:
        response = self.dispatch(raw)
        if response.output:
            print(response.output)
        return response.should_continue

    def dispatch(self, raw: str) -> TUIResponse:
        if raw in {"/quit", "/q", "/exit", "quit", "exit"}:
            return TUIResponse(should_continue=False)
        if raw in {"/help", "/commands"}:
            return TUIResponse(output=HELP)
        if raw == "/status":
            return TUIResponse(output=self.status())
        if raw == "/clear":
            return TUIResponse(output=self.startup_page())
        if raw == "/index":
            return TUIResponse(output=self.engine.index_summary())
        if raw.startswith("/explain "):
            path = self._resolve_path(raw.removeprefix("/explain ").strip())
            return TUIResponse(output=self.engine.explain_file_prompt(path))
        if raw.startswith("/yaml "):
            path = self._resolve_path(raw.removeprefix("/yaml ").strip())
            return TUIResponse(output=self.engine.review_yaml(path))
        if raw.startswith("/ask "):
            return TUIResponse(output=self.engine.ask_model(raw.removeprefix("/ask ").strip()))
        if raw.startswith("/"):
            return TUIResponse(output="Unknown command. Type /help.")
        return TUIResponse(output=self.engine.ask_model(raw))

    def status(self) -> str:
        return "\n".join(
            [
                "Jarvis-Agent status",
                f"- project: {self.config.project.root}",
                f"- project name: {self.config.project.name}",
                f"- model backend: {self.config.model.backend}",
                f"- model: {self.config.model.model}",
                f"- max tokens: {self.config.model.max_tokens}",
                f"- temperature: {self.config.model.temperature}",
            ]
        )

    def _resolve_path(self, value: str) -> Path:
        parts = shlex.split(value)
        if not parts:
            raise ValueError("Path is required.")
        path = Path(parts[0]).expanduser()
        if not path.is_absolute():
            path = self.config.project.root / path
        return path.resolve()
