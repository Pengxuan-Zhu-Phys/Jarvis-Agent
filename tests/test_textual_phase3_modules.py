import time
import unittest
from pathlib import Path

from jarvis_agent.branding import load_jarvis_branding
from jarvis_agent.textual_tui.animation import LogoMonitorConfig, current_monitor_widths, render_logo_monitor_frame
from jarvis_agent.textual_tui.composer import prompt_visual_line_count
from jarvis_agent.textual_tui.history import HistoryModel, TurnRecord, history_index_label, history_toggle_label, prompt_needs_expansion


class TextualPhase3ModuleTests(unittest.TestCase):
    def test_history_model_tracks_current_and_expansion(self) -> None:
        model = HistoryModel()
        record = TurnRecord(prompt="long prompt", timestamp="now", created_at=time.time())

        self.assertEqual(model.add_turn(record), 0)
        self.assertEqual(model.visible_turn_index(10, expanded=False), 0)
        self.assertTrue(model.toggle_prompt(0, max_prompt_chars=4))
        self.assertIn(0, model.expanded_turn_prompts)
        self.assertTrue(model.toggle_prompt(0, max_prompt_chars=4))
        self.assertNotIn(0, model.expanded_turn_prompts)

    def test_history_labels_and_prompt_expansion(self) -> None:
        self.assertEqual(history_toggle_label(3), "▸ 3")
        self.assertEqual(history_toggle_label(3, expanded=True), "▾ 3")
        self.assertEqual(history_index_label(3), "  3")
        self.assertTrue(prompt_needs_expansion("a\nb", max_prompt_chars=80))
        self.assertTrue(prompt_needs_expansion("abcdef", max_prompt_chars=3))
        self.assertFalse(prompt_needs_expansion("abc", max_prompt_chars=3))

    def test_prompt_visual_line_count_wraps(self) -> None:
        self.assertEqual(prompt_visual_line_count("", 10), 1)
        self.assertEqual(prompt_visual_line_count("abcdef", 3), 2)
        self.assertEqual(prompt_visual_line_count("ab\ncdef", 3), 3)

    def test_logo_monitor_animation_helpers(self) -> None:
        branding = load_jarvis_branding(Path("/tmp/not-a-jarvis-project"), command="definitely-not-jarvis")
        config = LogoMonitorConfig()

        frame = render_logo_monitor_frame(
            config.reveal_frames + config.monitor_frames,
            branding.logo_pattern,
            branding.logo_widths("left"),
            branding.logo_widths("right"),
            config,
        )

        self.assertIn("⬤", frame)
        self.assertEqual(
            current_monitor_widths("left", config.reveal_frames + config.monitor_frames, branding.logo_widths("left"), branding.logo_widths("right")),
            branding.logo_widths("left"),
        )
