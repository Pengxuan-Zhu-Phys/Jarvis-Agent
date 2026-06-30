from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shlex

from jarvis_agent.agent_actions import AGENT_SYSTEM_PROMPT, INDEX_ACTION_MARKER, detect_action_marker, detect_agent_action
from jarvis_agent.branding import load_jarvis_branding
from jarvis_agent.config import AVAILABLE_MODELS, AgentConfig, save_local_model_state
from jarvis_agent.session import SessionStore
from jarvis_agent.workflows import WorkflowEngine


HELP = """Commands:
  /help             show this help
  /home             show the Jarvis-Agent home page
  /status           show project and model status
  /model            list available local models
  /model N|REPO     switch the active MLX model
  /resume           list saved sessions
  /resume latest    show the latest saved session
  /index            index the configured project
  /explain PATH     build an explanation prompt for a file
  /yaml PATH        run a lightweight YAML review
  /ask PROMPT       send a prompt to the configured model
  /clear            clear the session output
  /quit             exit

Plain text without a leading slash is sent to the configured model.
"""


@dataclass(frozen=True)
class TUIResponse:
    should_continue: bool = True
    output: str = ""


class TerminalUI:
    def __init__(
        self,
        config: AgentConfig,
        engine: WorkflowEngine | None = None,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.engine = engine or WorkflowEngine(config)
        self.branding = load_jarvis_branding(config.project.root)
        self.session_store = session_store or SessionStore()
        self.session_id = session_id or self.session_store.new_session_id()
        self.session_store.append(self.session_id, "session_start", f"Project: {self.config.project.root}")

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
        width = 78
        rule = "=" * width
        version_block = _limit_lines(self.branding.compact_version_lines(), max_lines=10)
        recent = self.session_store.recent_session_ids(limit=1)
        latest = recent[0] if recent else "none"
        return "\n".join(
            [
                rule,
                self.branding.plain_logo(),
                *version_block,
                "",
                "Local assistant for HEP package understanding, YAML configuration,",
                "workflow automation, and MLX-backed Qwen3-Coder experiments.",
                f"Branding source: {self.branding.source}",
                "",
                f"Project : {self.config.project.root}",
                f"Model   : {self.config.model.backend}:{self.config.model.model}",
                f"History : {self.session_store.path}",
                f"Latest  : {latest}",
                "",
                "Start here:",
                "  /index                 scan the current HEP package",
                "  /yaml path.yaml         review a YAML configuration",
                "  /explain path/to/file   build a package-aware explanation prompt",
                "  /ask question           ask the local model",
                "  /model                 choose a local MLX model",
                "  /resume                show saved sessions",
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
        response = self._dispatch(raw)
        if self._should_record(raw):
            self.session_store.append(self.session_id, "user", raw)
            if response.output:
                self.session_store.append(self.session_id, "assistant", response.output)
        return response

    def _dispatch(self, raw: str) -> TUIResponse:
        if raw in {"/quit", "/q", "/exit", "quit", "exit"}:
            return TUIResponse(should_continue=False)
        if raw in {"/help", "/commands"}:
            return TUIResponse(output=HELP)
        if raw == "/home":
            return TUIResponse(output=self.startup_page())
        if raw == "/status":
            return TUIResponse(output=self.status())
        if raw == "/model":
            return TUIResponse(output=self.model_menu())
        if raw.startswith("/model "):
            return TUIResponse(output=self.switch_model(raw.removeprefix("/model ").strip()))
        if raw == "/resume":
            return TUIResponse(output=self.session_store.format_recent())
        if raw.startswith("/resume "):
            return TUIResponse(output=self.session_store.format_transcript(raw.removeprefix("/resume ").strip()))
        if raw == "/clear":
            return TUIResponse(output="Session output cleared.")
        if raw == "/index":
            return TUIResponse(output=self.engine.index_summary())
        if raw.startswith("/explain "):
            path = self._resolve_path(raw.removeprefix("/explain ").strip())
            return TUIResponse(output=self.engine.explain_file_prompt(path))
        if raw.startswith("/yaml "):
            path = self._resolve_path(raw.removeprefix("/yaml ").strip())
            return TUIResponse(output=self.engine.review_yaml(path))
        if raw.startswith("/ask "):
            return self.dispatch_natural_language(raw.removeprefix("/ask ").strip())
        if raw.startswith("/"):
            return TUIResponse(output="Unknown command. Type /help.")
        return self.dispatch_natural_language(raw)

    def dispatch_natural_language(self, text: str) -> TUIResponse:
        action = detect_agent_action(text)
        if action == "index":
            return TUIResponse(output=self.run_index_action("deterministic-intent"))
        model_output = self.engine.ask_model(with_agent_system_prompt(text))
        if detect_action_marker(model_output) == "index":
            return TUIResponse(output=self.run_index_action("model-marker"))
        return TUIResponse(output=model_output)

    def run_index_action(self, trigger: str) -> str:
        return "\n".join(
            [
                f"{INDEX_ACTION_MARKER}",
                f"[action-log] source={trigger} action=index",
                "正在执行项目索引，请稍候...",
                "",
                self.engine.index_summary(),
            ]
        )

    def _should_record(self, raw: str) -> bool:
        command = raw.split(maxsplit=1)[0] if raw else ""
        return command not in {"/clear", "/home", "/resume"}

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
                f"- session: {self.session_id}",
                f"- history: {self.session_store.path}",
            ]
        )

    def model_menu(self) -> str:
        lines = ["Available MLX models:"]
        for index, model in enumerate(AVAILABLE_MODELS, start=1):
            marker = "*" if model == self.config.model.model else " "
            lines.append(f"  {marker} {index}. {model}")
        lines.extend(
            [
                "",
                "Use /model N to switch by number, or /model HF_REPO to use a custom MLX model.",
                f"Current: {self.config.model.backend}:{self.config.model.model}",
            ]
        )
        return "\n".join(lines)

    def switch_model(self, selector: str) -> str:
        if not selector:
            return self.model_menu()
        model = self._resolve_model_selector(selector)
        self.config = replace(self.config, model=replace(self.config.model, model=model))
        self.engine = WorkflowEngine(self.config)
        state_path = save_local_model_state(self.config)
        return f"Switched model to {self.config.model.backend}:{model}\nSaved model state to {state_path}"

    def _resolve_model_selector(self, selector: str) -> str:
        if selector.isdigit():
            index = int(selector)
            if not 1 <= index <= len(AVAILABLE_MODELS):
                raise ValueError(f"Model index must be between 1 and {len(AVAILABLE_MODELS)}.")
            return AVAILABLE_MODELS[index - 1]
        return selector

    def _resolve_path(self, value: str) -> Path:
        parts = shlex.split(value)
        if not parts:
            raise ValueError("Path is required.")
        path = Path(parts[0]).expanduser()
        if not path.is_absolute():
            path = self.config.project.root / path
        return path.resolve()


def _limit_lines(lines: tuple[str, ...], max_lines: int) -> tuple[str, ...]:
    if len(lines) <= max_lines:
        return lines
    return (*lines[: max_lines - 1], f"... [{len(lines) - max_lines + 1} more Jarvis -v lines]")


def with_agent_system_prompt(user_text: str) -> str:
    return f"{AGENT_SYSTEM_PROMPT}\n\nUser: {user_text}"
