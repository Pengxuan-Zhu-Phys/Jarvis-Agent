import asyncio
import io
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jarvis_agent.agent_actions import INDEX_ACTION_MARKER, detect_agent_action
from jarvis_agent.config import AVAILABLE_MODELS, AgentConfig, JARVIS_HOME_ENV, ModelConfig, ProjectConfig, compact_model_name, model_badge_name
from jarvis_agent.session import SessionStore
from jarvis_agent.tui import TerminalUI
from jarvis_agent.textual_tui import (
    _compact_middle_path,
    _compact_path,
    _format_token_count,
    _home_relative_path,
    _relative_time_label,
    compact_metrics,
    estimate_context_tokens,
    location_to_text_index,
    pacman_ghost_frame,
    parse_context_metric_tokens,
    ping_pong_offset,
    slash_suggestion_context,
    split_output_metrics,
    split_output_metrics_detail,
    text_index_to_location,
    wrap_plain_text,
)
from jarvis_agent.textual_tui.output.transcript import TranscriptView
from jarvis_agent.textual_tui.output.widgets import AssistantBlock, ErrorBlock, SummaryBlock, UserBlock


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
        home_dir = tempfile.TemporaryDirectory()
        self.addCleanup(home_dir.cleanup)
        env_patch = patch.dict(os.environ, {JARVIS_HOME_ENV: home_dir.name})
        env_patch.start()
        self.addCleanup(env_patch.stop)
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

    def test_model_scan_discovers_and_saves_models(self) -> None:
        tui, _ = self.make_tui()

        with patch("jarvis_agent.tui.discover_mlx_models", return_value=("mlx-community/New-Coder-4bit",)):
            response = tui.dispatch("/model scan")

        self.assertIn("Discovered 1 downloaded MLX-LM model", response.output)
        self.assertIn("mlx-community/New-Coder-4bit", response.output)
        self.assertIn("Saved global model state", response.output)

        menu = tui.dispatch("/model").output
        self.assertIn("mlx-community/New-Coder-4bit", menu)

    def test_plain_text_is_sent_to_model(self) -> None:
        tui, engine = self.make_tui()

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(tui.handle("explain this package"))

        self.assertEqual(len(engine.prompts), 1)
        self.assertIn("User: explain this package", engine.prompts[0])
        self.assertIn("User: explain this package", output.getvalue())

    def test_dispatch_can_skip_session_recording(self) -> None:
        tui, _ = self.make_tui()

        response = tui.dispatch("do not record this", record=False)

        self.assertIn("answer:", response.output)
        transcript = tui.dispatch("/resume latest").output
        self.assertNotIn("do not record this", transcript)

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

    def test_textual_home_mounts_logo_monitor(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        config, _, _ = self.make_textual_app_parts()

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test() as pilot:
                await pilot.pause()
                logo = pilot.app.query_one("#logo-monitor")
                home = pilot.app.query_one("#home-panel")
                self.assertIn("⬤", str(logo.render()))
                home_text = str(home.render())
                self.assertIn("Just a Robust and Versatile Interface Suite for HEP", home_text)
                self.assertIn("Version:", home_text)

        asyncio.run(run_smoke())

    def test_textual_submit_prompt_appends_user_and_assistant_blocks(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        config, engine, store = self.make_textual_app_parts()
        engine.model_response = "answer\n```python\nprint('ok')\n```"

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test() as pilot:
                pilot.app.ui = TerminalUI(config, engine=engine, session_store=store, session_id="textual-test")
                pilot.app.RESPONSE_STREAM_SECONDS_PER_CHAR = 0.0001
                prompt = pilot.app.query_one("#prompt")
                prompt.load_text("hello")
                pilot.app.submit_prompt()
                for _ in range(80):
                    await pilot.pause(0.01)
                    if not pilot.app.is_generation_active():
                        break
                transcript = pilot.app.query_one("#log", TranscriptView)
                self.assertEqual(len(transcript.query(UserBlock).nodes), 1)
                self.assertEqual(len(transcript.query(AssistantBlock).nodes), 1)
                self.assertEqual(pilot.app.query_one("#stop-button").styles.display, "none")
                self.assertIn(":", str(pilot.app.query_one("#token-counter").render()))
                transcript_text = store.format_transcript("textual-test")
                self.assertIn("user\nhello", transcript_text)
                self.assertIn("assistant\nanswer", transcript_text)

        asyncio.run(run_smoke())

    def test_textual_thinking_status_is_compact_with_input_tokens(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        config, _, _ = self.make_textual_app_parts()

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test() as pilot:
                pilot.app.thinking_started_at = time.monotonic() - 1.2
                pilot.app.thinking_context_tokens = 12
                pilot.app.update_thinking_status()
                await pilot.pause()

                status = str(pilot.app.query_one("#thinking").render())
                self.assertIn("Thinking...", status)
                self.assertIn("1.", status)
                self.assertNotIn("context", status)
                self.assertNotIn("max gen", status)
                self.assertIn("↑12", str(pilot.app.query_one("#token-counter").render()))
                self.assertEqual(pilot.app.query_one("#stop-button").styles.display, "block")

        asyncio.run(run_smoke())

    def test_textual_run_control_right_aligns_with_composer(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        config, _, _ = self.make_textual_app_parts()

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test(size=(120, 30)) as pilot:
                pilot.app.update_run_control()
                await pilot.pause()

                composer = pilot.app.query_one("#composer")
                run_control = pilot.app.query_one("#run-control")
                composer_right = composer.region.x + composer.region.width
                run_control_right = run_control.region.x + run_control.region.width
                self.assertEqual(run_control_right, composer_right)

        asyncio.run(run_smoke())

    def test_textual_stop_button_cancels_response_stream(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        config, engine, store = self.make_textual_app_parts()
        engine.model_response = "\n".join(f"line {index}" for index in range(300))

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test() as pilot:
                pilot.app.ui = TerminalUI(config, engine=engine, session_store=store, session_id="textual-test")
                pilot.app.RESPONSE_STREAM_SECONDS_PER_CHAR = 0.01
                prompt = pilot.app.query_one("#prompt")
                prompt.load_text("hello")
                pilot.app.submit_prompt()
                while pilot.app.thinking_started_at is not None:
                    await pilot.pause(0.01)
                await pilot.pause(0.02)
                self.assertTrue(pilot.app.is_generation_active())
                self.assertEqual(pilot.app.query_one("#stop-button").styles.display, "block")
                self.assertIn("↓", str(pilot.app.query_one("#token-counter").render()))
                self.assertNotIn("|", str(pilot.app.query_one("#thinking").render()))

                pilot.app.stop_generation()
                await pilot.pause()

                self.assertFalse(pilot.app.is_generation_active())
                self.assertEqual(pilot.app.query_one("#stop-button").styles.display, "none")
                self.assertIn(":", str(pilot.app.query_one("#token-counter").render()))

        asyncio.run(run_smoke())

    def test_textual_stop_thinking_ignores_stale_background_result(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        class BlockingEngine(FakeEngine):
            def __init__(self) -> None:
                super().__init__()
                self.first_started = threading.Event()
                self.release_first = threading.Event()

            def ask_model(self, prompt: str) -> str:
                self.prompts.append(prompt)
                if len(self.prompts) == 1:
                    self.first_started.set()
                    self.release_first.wait(timeout=2)
                    return "first answer should be ignored"
                return "second answer"

        config, _, store = self.make_textual_app_parts()
        engine = BlockingEngine()

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test() as pilot:
                pilot.app.ui = TerminalUI(config, engine=engine, session_store=store, session_id="textual-test")
                pilot.app.RESPONSE_STREAM_SECONDS_PER_CHAR = 0.0001
                prompt = pilot.app.query_one("#prompt")
                prompt.load_text("first prompt")
                pilot.app.submit_prompt()
                for _ in range(100):
                    if engine.first_started.is_set():
                        break
                    await pilot.pause(0.01)
                self.assertTrue(engine.first_started.is_set())
                self.assertTrue(pilot.app.is_generation_active())

                pilot.app.stop_generation()
                await pilot.pause()
                self.assertFalse(pilot.app.is_generation_active())

                prompt.load_text("second prompt")
                pilot.app.submit_prompt()
                for _ in range(100):
                    await pilot.pause(0.01)
                    if not pilot.app.is_generation_active() and len(engine.prompts) >= 2:
                        break
                engine.release_first.set()
                await pilot.pause(0.05)

                transcript_text = store.format_transcript("textual-test")
                self.assertIn("second prompt", transcript_text)
                self.assertIn("second answer", transcript_text)
                self.assertNotIn("first prompt", transcript_text)
                self.assertNotIn("first answer should be ignored", transcript_text)

        try:
            asyncio.run(run_smoke())
        finally:
            engine.release_first.set()

    def test_textual_index_and_unknown_commands_render_structured_blocks(self) -> None:
        from jarvis_agent.textual_tui.app import JarvisAgentApp

        config, engine, store = self.make_textual_app_parts()

        async def run_smoke() -> None:
            async with JarvisAgentApp(config).run_test() as pilot:
                pilot.app.ui = TerminalUI(config, engine=engine, session_store=store, session_id="textual-test")
                pilot.app.process_raw("/index")
                await pilot.pause()
                transcript = pilot.app.query_one("#log", TranscriptView)
                self.assertEqual(len(transcript.query(UserBlock).nodes), 1)
                self.assertEqual(len(transcript.query(SummaryBlock).nodes), 1)

                pilot.app.process_raw("/nope")
                await pilot.pause()
                transcript = pilot.app.query_one("#log", TranscriptView)
                self.assertEqual(len(transcript.query(UserBlock).nodes), 1)
                self.assertEqual(len(transcript.query(ErrorBlock).nodes), 1)

        asyncio.run(run_smoke())

    def make_textual_app_parts(self) -> tuple[AgentConfig, FakeEngine, SessionStore]:
        home_dir = tempfile.TemporaryDirectory()
        self.addCleanup(home_dir.cleanup)
        env_patch = patch.dict(os.environ, {JARVIS_HOME_ENV: home_dir.name})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        config = AgentConfig(
            project=ProjectConfig(root=Path("/tmp/hep-package"), name="hep-package"),
            model=ModelConfig(model="local-model"),
        )
        engine = FakeEngine()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        store = SessionStore(Path(temp_dir.name) / "sessions.jsonl")
        return config, engine, store

    def test_estimate_context_tokens(self) -> None:
        self.assertEqual(estimate_context_tokens(""), 0)
        self.assertEqual(estimate_context_tokens("abcd"), 1)
        self.assertEqual(estimate_context_tokens("a" * 40), 10)

    def test_compact_display_helpers(self) -> None:
        self.assertEqual(compact_model_name("mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"), "Qwen3-Coder-30B-A3B-Instruct-4bit")
        self.assertEqual(model_badge_name("mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"), "Qwen3 Coder 30B")
        self.assertEqual(
            model_badge_name("mlx-community/Josiefied-Qwen2.5-Coder-7B-Instruct-abliterated-v1-4bit"),
            "Qwen2.5 Coder 7B",
        )
        self.assertEqual(_format_token_count(1_234), "1.2K")
        self.assertEqual(_format_token_count(10_500), "10.5K")
        self.assertEqual(_format_token_count(158_200), "158K")
        self.assertEqual(_format_token_count(2048), "2K")
        self.assertEqual(_format_token_count(999), "999")
        self.assertEqual(_compact_middle_path("~/Jarvis-Workshop/Jarvis-Examples/Eggbox", 24), "~/Jarvis-Worksh...Eggbox")
        self.assertTrue(_home_relative_path(Path.home()).startswith("~"))
        self.assertTrue(_compact_path("/" + "a" * 80).startswith("..."))
        metrics_text = (
            "Hello!\n\n"
            "[metrics] prompt: 424 tokens @ 390.93 tok/s | generation: 10 tokens @ 56.27 tok/s | context:\n"
            " 434 tokens | peak memory: 4.81 GB"
        )
        body, metrics = split_output_metrics(metrics_text)
        self.assertEqual(body, "Hello!")
        self.assertEqual(metrics, "prompt 424 tok · gen 10 tok · ctx 434 tok · mem 4.81 GB")
        body, metrics, detail = split_output_metrics_detail(metrics_text)
        self.assertEqual(body, "Hello!")
        self.assertEqual(metrics, "prompt 424 tok · gen 10 tok · ctx 434 tok · mem 4.81 GB")
        self.assertIn("390.93 tok/s", detail)
        self.assertEqual(compact_metrics("prompt: 12 tokens | context: 20 tokens"), "prompt 12 tok · ctx 20 tok")
        self.assertEqual(parse_context_metric_tokens(detail), 434)
        self.assertEqual(parse_context_metric_tokens("prompt: 954 tokens | generation: 359 tokens | context: 1313 tokens"), 1313)
        self.assertIsNone(parse_context_metric_tokens("prompt: 12 tokens | generation: 3 tokens"))
        self.assertEqual(_relative_time_label(time.time() - 65), "1 min")
        self.assertEqual(_relative_time_label(time.time()), "now")
        self.assertEqual(ping_pong_offset(0, 15), 0)
        self.assertEqual(ping_pong_offset(15, 15), 15)
        self.assertEqual(ping_pong_offset(16, 15), 14)
        self.assertEqual(pacman_ghost_frame(15, max_spaces=15), "               👻 👻 👻")
        self.assertEqual(slash_suggestion_context("Hi, /qu", 7), (4, 7, "/qu"))
        self.assertEqual(slash_suggestion_context("Hi, /qu there", 7), (4, 7, "/qu"))
        self.assertEqual(slash_suggestion_context("/model", 6), (0, 6, "/model"))
        self.assertIsNone(slash_suggestion_context("Hi there", 8))
        self.assertIsNone(slash_suggestion_context("Hi, /quit now", 13))
        self.assertEqual(text_index_to_location("ab\ncde", 4), (1, 1))
        self.assertEqual(location_to_text_index("ab\ncde", (1, 2)), 5)
        self.assertEqual(wrap_plain_text("abcdef", 3), ["abc", "def"])
        self.assertEqual(wrap_plain_text("ab\ncdef", 3), ["ab", "cde", "f"])
