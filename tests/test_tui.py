import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jarvis_agent import textual_tui
from jarvis_agent.agent_actions import INDEX_ACTION_MARKER, detect_agent_action
from jarvis_agent.config import AVAILABLE_MODELS, AgentConfig, ModelConfig, ProjectConfig
from jarvis_agent.session import SessionStore
from jarvis_agent.tui import TerminalUI
from jarvis_agent.textual_tui import _compact_model_name, _compact_path, estimate_context_tokens


class FakeEngine:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.model_response = ""

    def index_summary(self) -> str:
        return (
            "项目索引已完成。\n\n"
            "Summary\n"
            "- scanned files: 3\n"
            "- updated files: 1\n"
            "- unchanged files: 2\n"
            "- removed files: 0\n"
            "- symbols: 7\n"
            "- references: 4\n"
            "- elapsed: 0.10s\n"
            "- cache: /tmp/hep-package/.jarvis/index/codebase_index.json"
        )

    def explain_file_prompt(self, path: Path) -> str:
        return f"explain:{path.name}"

    def review_yaml(self, path: Path) -> str:
        return f"yaml:{path.name}"

    def ask_model(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.model_response:
            return self.model_response
        return f"answer:{prompt}"


class TUITests(unittest.TestCase):
    def make_tui(self) -> tuple[TerminalUI, FakeEngine]:
        config = AgentConfig(
            project=ProjectConfig(root=Path("/tmp/hep-package"), name="hep-package"),
            model=ModelConfig(model="local-model"),
        )
        engine = FakeEngine()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        store = SessionStore(Path(temp_dir.name) / "sessions.jsonl")
        return TerminalUI(config, engine=engine, session_store=store, session_id="test-session"), engine

    def test_startup_page_uses_slash_commands(self) -> None:
        tui, _ = self.make_tui()
        page = tui.startup_page()

        self.assertIn("/index", page)
        self.assertIn("/yaml path.yaml", page)
        self.assertIn("/model", page)
        self.assertIn("/resume", page)
        self.assertIn("Just a Robust and Versatile Interface Suite for HEP", page)
        self.assertNotIn("Jarvis-Agent for Jarvis-HEP", page)
        self.assertNotIn("/version", page)
        self.assertNotIn(":index", page)
        self.assertNotIn("Online docs", page)
        self.assertNotIn("Homepage", page)
        self.assertNotIn("arXiv", page)

    def test_help_uses_slash_commands(self) -> None:
        tui, _ = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("/help"))

        text = output.getvalue()
        self.assertIn("/help", text)
        self.assertIn("/home", text)
        self.assertIn("/model", text)
        self.assertIn("/resume", text)
        self.assertIn("/quit", text)
        self.assertNotIn("/version", text)
        self.assertNotIn(":help", text)

    def test_home_command_returns_startup_page(self) -> None:
        tui, _ = self.make_tui()
        response = tui.dispatch("/home")

        self.assertTrue(response.should_continue)
        self.assertIn("Just a Robust and Versatile Interface Suite for HEP", response.output)
        self.assertNotIn("Jarvis-Agent for Jarvis-HEP", response.output)

    def test_model_command_lists_and_switches_models(self) -> None:
        tui, _ = self.make_tui()

        menu = tui.dispatch("/model").output
        self.assertIn(AVAILABLE_MODELS[0], menu)
        self.assertIn(AVAILABLE_MODELS[1], menu)

        response = tui.dispatch("/model 2")
        self.assertIn(AVAILABLE_MODELS[1], response.output)
        self.assertEqual(tui.config.model.model, AVAILABLE_MODELS[1])

    def test_plain_text_is_sent_to_model(self) -> None:
        tui, engine = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("explain this package"))

        self.assertEqual(len(engine.prompts), 1)
        self.assertIn("User: explain this package", engine.prompts[0])
        self.assertIn("User: explain this package", output.getvalue())

    def test_natural_language_index_intent_runs_index_action(self) -> None:
        tui, engine = self.make_tui()

        response = tui.dispatch("帮我把当前项目索引一下")

        self.assertEqual(engine.prompts, [])
        self.assertIn(INDEX_ACTION_MARKER, response.output)
        self.assertIn("[action-log] source=deterministic-intent action=index", response.output)
        self.assertIn("正在执行项目索引，请稍候", response.output)
        self.assertIn("项目索引已完成", response.output)
        self.assertIn("scanned files: 3", response.output)
        self.assertIn(".jarvis/index/codebase_index.json", response.output)

    def test_ask_index_intent_runs_index_action(self) -> None:
        tui, engine = self.make_tui()

        response = tui.dispatch("/ask 更新一下代码索引")

        self.assertEqual(engine.prompts, [])
        self.assertIn("[action-log] source=deterministic-intent action=index", response.output)
        self.assertIn("updated files: 1", response.output)

    def test_model_marker_index_action_logs_model_source(self) -> None:
        tui, engine = self.make_tui()
        engine.model_response = INDEX_ACTION_MARKER

        response = tui.dispatch("please decide what to do")

        self.assertEqual(len(engine.prompts), 1)
        self.assertIn("[action-log] source=model-marker action=index", response.output)
        self.assertIn("scanned files: 3", response.output)

    def test_agent_action_detector_recognizes_index_phrases(self) -> None:
        self.assertEqual(detect_agent_action("扫描一下这个项目的代码结构"), "index")
        self.assertEqual(detect_agent_action("rebuild symbols"), "index")
        self.assertIsNone(detect_agent_action("解释一下这个项目"))

    def test_slash_commands_dispatch(self) -> None:
        tui, _ = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("/index"))
            self.assertTrue(tui.handle("/yaml config.yaml"))
            self.assertTrue(tui.handle("/explain src/main.cpp"))

        text = output.getvalue()
        self.assertIn("scanned files: 3", text)
        self.assertIn("yaml:config.yaml", text)
        self.assertIn("explain:main.cpp", text)

    def test_session_history_records_and_resumes(self) -> None:
        tui, _ = self.make_tui()
        tui.dispatch("explain this package")

        transcript = tui.dispatch("/resume latest").output
        self.assertIn("explain this package", transcript)
        self.assertIn("User: explain this package", transcript)

    def test_textual_home_uses_round_dot_monitor(self) -> None:
        source = Path(textual_tui.__file__).read_text(encoding="utf-8")

        self.assertIn("⬤", source)
        self.assertIn("left_background = \"#2f7fd8\"", source)
        self.assertIn("left_active = \"#ffffff\"", source)
        self.assertIn("right_background = \"#134a8d\"", source)
        self.assertIn("right_active = \"#f6d33f\"", source)
        self.assertIn("width: 16;", source)
        self.assertIn("height: 8;", source)
        self.assertIn("content-align: left top;", source)
        self.assertNotIn("██[/]", source)
        self.assertIn("TEXT_GRADIENT_COLORS", source)
        self.assertIn("render_colored_version_lines", source)
        self.assertIn("render_home_panel", source)
        self.assertIn("COMMAND_CHOICES", source)
        self.assertIn("ListView(id=\"suggestions\")", source)
        self.assertIn("on_input_changed", source)
        self.assertIn("on_key", source)
        self.assertIn("event.key == \"tab\"", source)
        self.assertIn("event.key in {\"up\", \"down\"}", source)
        self.assertIn("choose_model_suggestion", source)
        self.assertIn("on_list_view_selected", source)
        self.assertIn("Thinking...", source)
        self.assertIn("threading.Thread", source)
        self.assertIn("auto_copy_selection", source)
        self.assertIn("copy_to_clipboard(selection)", source)
        self.assertIn("Copied selection", source)
        self.assertIn("Screen > .screen--selection", source)
        self.assertIn("background: #ffe45c;", source)
        self.assertIn("color: #101216;", source)
        self.assertIn("render_turn_panel", source)
        self.assertIn("render_model_info", source)
        self.assertIn("Log(id=\"log\", highlight=False)", source)
        self.assertIn("show_horizontal_scrollbar = False", source)
        self.assertIn("scrollbar-size-horizontal: 0;", source)
        self.assertIn("on_resize", source)
        self.assertIn("reflow_output", source)
        self.assertIn("output_raw_text", source)
        self.assertIn("write_wrapped_output", source)
        self.assertIn("output_wrap_width", source)
        self.assertIn("wrap_output_text", source)
        self.assertIn("cell_len", source)
        self.assertIn("start_response_stream", source)
        self.assertIn("update_response_stream", source)
        self.assertIn("Responding...", source)
        self.assertIn("tokens/sec", source)
        self.assertNotIn("chars/s", source)
        self.assertIn("RESPONSE_STREAM_SECONDS_PER_CHAR", source)
        self.assertNotIn("Markdown(output)", source)
        self.assertNotIn("/version", source)
        self.assertIn("/home", source)
        self.assertIn("/model", source)
        self.assertIn("/resume", source)
        self.assertIn("#topbar", source)
        self.assertIn("#model-info", source)

    def test_estimate_context_tokens(self) -> None:
        self.assertEqual(estimate_context_tokens(""), 0)
        self.assertEqual(estimate_context_tokens("abcd"), 1)
        self.assertEqual(estimate_context_tokens("a" * 40), 10)

    def test_compact_display_helpers(self) -> None:
        self.assertEqual(_compact_model_name("mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"), "Qwen3-Coder-30B-A3B-Instruct-4bit")
        self.assertTrue(_compact_path("/" + "a" * 80).startswith("..."))
