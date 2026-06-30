import io
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jarvis_agent import textual_tui
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
)


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
        self.assertIn("margin-top: 3;", source)
        self.assertIn("border: round #4f7cff;", source)
        self.assertIn("border: round #303745;", source)
        self.assertNotIn("██[/]", source)
        self.assertIn("TEXT_GRADIENT_COLORS", source)
        self.assertIn("render_colored_version_lines", source)
        self.assertIn("render_home_panel", source)
        self.assertIn("COMMAND_CHOICES", source)
        self.assertIn("ListView(id=\"suggestions\")", source)
        self.assertIn("ListView(id=\"turn-history\")", source)
        self.assertIn("PromptTextArea", source)
        self.assertIn("PromptTextArea(", source)
        self.assertIn("on_text_area_changed", source)
        self.assertIn("PROMPT_MAX_LINES = 5", source)
        self.assertIn("update_composer_height", source)
        self.assertIn("prompt_visual_line_count", source)
        self.assertIn("show_vertical_scrollbar = total_lines > self.PROMPT_MAX_LINES", source)
        self.assertIn("composer.styles.height = visible_lines + 2", source)
        self.assertIn("event.key == \"shift+enter\"", source)
        self.assertNotIn("event.key == \"ctrl+j\"", source)
        self.assertIn("submit_prompt", source)
        self.assertIn("on_key", source)
        self.assertIn("event.key == \"tab\"", source)
        self.assertIn("set_prompt_value", source)
        self.assertIn("text_index_to_location", source)
        self.assertIn("location_to_text_index", source)
        self.assertIn("event.key in {\"up\", \"down\"}", source)
        self.assertIn("choose_model_suggestion", source)
        self.assertIn("on_list_view_selected", source)
        self.assertIn("Thinking...", source)
        self.assertIn("threading.Thread", source)
        self.assertIn("auto_copy_selection", source)
        self.assertIn("copy_to_clipboard(selection)", source)
        self.assertIn("Copied selection", source)
        self.assertIn("Screen > .screen--selection", source)
        self.assertIn("background: #F6D33E;", source)
        self.assertIn("background: rgba(39, 51, 73, 0.3);", source)
        self.assertNotIn("background: #273349;", source)
        self.assertNotIn("background: #ffe45c;", source)
        self.assertIn("color: #101216;", source)
        self.assertIn("render_turn_panel", source)
        self.assertIn("render_model_info", source)
        self.assertIn("model_badge_name", source)
        self.assertIn("id=\"composer\"", source)
        self.assertIn("border: round #6d5cae;", source)
        self.assertIn("padding: 1 2 6 2;", source)
        self.assertIn("layers: base popup composer;", source)
        self.assertIn("dock: bottom;", source)
        self.assertIn("layer: composer;", source)
        self.assertIn("layer: popup;", source)
        self.assertIn("margin: 0 2 3 2;", source)
        self.assertIn("margin: 0 2 4 2;", source)
        self.assertIn("#output-metrics", source)
        self.assertIn("Static(\"\", id=\"output-metrics\")", source)
        self.assertIn("width: auto;", source)
        self.assertIn("margin: 0 0 6 0;", source)
        self.assertIn("#pacman-ghosts", source)
        self.assertIn("Static(\"\", id=\"pacman-ghosts\")", source)
        self.assertIn("width: 28;", source)
        self.assertIn("margin: 0 0 3 0;", source)
        self.assertIn("#ghost-clock", source)
        self.assertIn("Static(\"\", id=\"ghost-clock\")", source)
        self.assertIn("width: 10;", source)
        self.assertIn("id=\"prompt-icon\"", source)
        self.assertIn("Static(\"❱\", id=\"prompt-icon\")", source)
        self.assertIn("border-subtitle-align: right;", source)
        self.assertIn("border-subtitle-color: #8d93a1;", source)
        self.assertIn("border-subtitle-background: transparent;", source)
        self.assertIn("update_composer_caption", source)
        self.assertIn("border_subtitle", source)
        self.assertIn("#git-status-info", source)
        self.assertIn("#repo-path-info", source)
        self.assertIn("#repo-path-info:hover", source)
        self.assertIn("copy_project_path", source)
        self.assertIn("render_git_status_info", source)
        self.assertIn("render_repo_path_info", source)
        self.assertIn("repo_path_max_chars", source)
        self.assertIn("update_repo_path_info", source)
        self.assertIn("overlay: screen;", source)
        self.assertIn("border: round #303745;", source)
        self.assertIn("width: 76;", source)
        self.assertIn("constrain: inside inside;", source)
        self.assertIn("position_suggestions", source)
        self.assertIn("suggestions.styles.offset", source)
        self.assertIn("slash_suggestion_context", source)
        self.assertIn("suggestion_start", source)
        self.assertIn("suggestion_end", source)
        self.assertIn("replace_suggestion_token", source)
        self.assertIn("#context-info", source)
        self.assertIn("#todo-info", source)
        self.assertIn("CONTEXT_LIMIT_TOKENS", source)
        self.assertIn("render_repo_info", source)
        self.assertIn("render_context_info", source)
        self.assertIn("render_context_progress", source)
        self.assertIn("context_info.is_mouse_over", source)
        self.assertIn("measured_context_tokens", source)
        self.assertIn("parse_context_metric_tokens", source)
        self.assertIn("self.measured_context_tokens = context_tokens", source)
        self.assertIn("context_tokens: int | None = None", source)
        self.assertIn("record.context_tokens", source)
        self.assertIn("width: 12;", source)
        self.assertIn("min-width: 12;", source)
        self.assertIn("CONTEXT_LIMIT_TOKENS = 2048", source)
        self.assertIn("label.rjust(self.context_info_width())", source)
        self.assertIn("Text(label.rjust(width)", source)
        self.assertIn("(self.output_raw_text, self.thinking_prompt)", source)
        self.assertNotIn("(self.output_raw_text, self.thinking_prompt, self.response_text)", source)
        self.assertIn("on #4A3F13", source)
        self.assertIn("set_interval(0.20, self.update_context_info)", source)
        self.assertIn("context_info.tooltip = None", source)
        self.assertIn("render_todo_info", source)
        self.assertIn("toggle_todo_panel", source)
        self.assertIn("TurnRecord", source)
        self.assertIn("created_at", source)
        self.assertIn("metrics: str", source)
        self.assertIn("start_new_turn", source)
        self.assertIn("reset_output_box", source)
        self.assertIn("update_current_turn_output", source)
        self.assertIn("refresh_history_panel", source)
        self.assertIn("history.border_title = \" Turns \"", source)
        self.assertIn(".history-row", source)
        self.assertIn(".history-prompt", source)
        self.assertIn(".history-time", source)
        self.assertIn("history_record_row", source)
        self.assertIn("Static(relative, classes=\"history-time\")", source)
        self.assertIn("history_expanded", source)
        self.assertIn("history_pinned", source)
        self.assertIn("self.history_pinned = True", source)
        self.assertIn("action_toggle_history", source)
        self.assertIn("collapse_history", source)
        self.assertIn("event.key == \"escape\"", source)
        self.assertIn("(\"ctrl+h\", \"toggle_history\", \"History\")", source)
        self.assertIn("_relative_time_label", source)
        self.assertIn("_exact_time_label", source)
        self.assertIn("exit_on_error=False", source)
        self.assertIn("history.is_mounted", source)
        self.assertIn("apply_history_selection", source)
        self.assertIn("show_output_snapshot", source)
        self.assertIn("split_output_metrics", source)
        self.assertIn("split_output_metrics_detail", source)
        self.assertIn("compact_metrics", source)
        self.assertIn("set_output_metrics", source)
        self.assertIn("update_output_metrics_caption", source)
        self.assertIn("clear_output_metrics_caption", source)
        self.assertIn("refresh_output_metrics_visibility", source)
        self.assertIn("output_metrics_display_text", source)
        self.assertIn("position_output_metrics_caption", source)
        self.assertIn("caption.styles.offset", source)
        self.assertIn("animate_pacman_ghosts", source)
        self.assertIn("set_interval(0.35, self.animate_pacman_ghosts)", source)
        self.assertIn("render_pacman_ghosts", source)
        self.assertIn("position_pacman_ghosts", source)
        self.assertIn("GHOST_TRACK_SPACES = 15", source)
        self.assertIn("GHOST_WIDTH = 28", source)
        self.assertIn("GHOST_CLOCK_WIDTH = 10", source)
        self.assertIn("set_interval(1.0, self.update_ghost_clock)", source)
        self.assertIn("update_ghost_clock", source)
        self.assertIn("position_ghost_clock", source)
        self.assertIn("clock.update(current_time_label())", source)
        self.assertIn("pacman_ghost_frame", source)
        self.assertIn("ping_pong_offset", source)
        self.assertIn("👻 👻 👻", source)
        self.assertIn("is_generation_active", source)
        self.assertIn("History preview is paused", source)
        self.assertIn("metrics_detail", source)
        self.assertIn("set_chat_visible", source)
        self.assertIn("tooltip", source)
        self.assertIn("is_mouse_over", source)
        self.assertIn("get_git_info", source)
        self.assertIn("_home_relative_path", source)
        self.assertIn("_compact_middle_path", source)
        self.assertIn("_format_token_count", source)
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
        self.assertIn("ARC_SPINNER_FRAMES", source)
        self.assertIn("(\"◜\", \"◟\", \"◞\", \"◝\")", source)
        self.assertIn("Responding...", source)
        self.assertIn("f\"{frame} Responding...", source)
        self.assertNotIn("↳ Responding...", source)
        self.assertIn("tokens/sec", source)
        self.assertNotIn("chars/s", source)
        self.assertIn("RESPONSE_STREAM_SECONDS_PER_CHAR", source)
        self.assertNotIn("Markdown(output)", source)
        self.assertNotIn("/version", source)
        self.assertIn("/home", source)
        self.assertIn("/model", source)
        self.assertIn("/resume", source)
        self.assertIn("#topbar", source)
        self.assertNotIn("#model-info", source)
        self.assertNotIn("query_one(\"#turn\", Static)", source)

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
