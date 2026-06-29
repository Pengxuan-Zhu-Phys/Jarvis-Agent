import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jarvis_agent.config import AgentConfig, ModelConfig, ProjectConfig
from jarvis_agent.tui import TerminalUI


class FakeEngine:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def index_summary(self) -> str:
        return "3 indexed files"

    def explain_file_prompt(self, path: Path) -> str:
        return f"explain:{path.name}"

    def review_yaml(self, path: Path) -> str:
        return f"yaml:{path.name}"

    def ask_model(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"answer:{prompt}"


class TUITests(unittest.TestCase):
    def make_tui(self) -> tuple[TerminalUI, FakeEngine]:
        config = AgentConfig(
            project=ProjectConfig(root=Path("/tmp/hep-package"), name="hep-package"),
            model=ModelConfig(model="local-model"),
        )
        engine = FakeEngine()
        return TerminalUI(config, engine=engine), engine

    def test_startup_page_uses_slash_commands(self) -> None:
        tui, _ = self.make_tui()
        page = tui.startup_page()

        self.assertIn("Jarvis-Agent Build", page)
        self.assertIn("/index", page)
        self.assertIn("/yaml path.yaml", page)
        self.assertNotIn(":index", page)

    def test_help_uses_slash_commands(self) -> None:
        tui, _ = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("/help"))

        text = output.getvalue()
        self.assertIn("/help", text)
        self.assertIn("/quit", text)
        self.assertNotIn(":help", text)

    def test_plain_text_is_sent_to_model(self) -> None:
        tui, engine = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("explain this package"))

        self.assertEqual(engine.prompts, ["explain this package"])
        self.assertIn("answer:explain this package", output.getvalue())

    def test_slash_commands_dispatch(self) -> None:
        tui, _ = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("/index"))
            self.assertTrue(tui.handle("/yaml config.yaml"))
            self.assertTrue(tui.handle("/explain src/main.cpp"))

        text = output.getvalue()
        self.assertIn("3 indexed files", text)
        self.assertIn("yaml:config.yaml", text)
        self.assertIn("explain:main.cpp", text)
