import unittest

from jarvis_agent.textual_tui.output.blocks import split_segments


class OutputBlockTests(unittest.TestCase):
    def test_split_segments_detects_prose_and_code(self) -> None:
        text = "Intro\n```python\nprint('hi')\n```\nOutro"

        segments = split_segments(text)

        self.assertEqual([segment.kind for segment in segments], ["prose", "code", "prose"])
        self.assertEqual(segments[1].language, "python")
        self.assertIn("print", segments[1].text)

    def test_split_segments_is_cached(self) -> None:
        text = "Same text\n```yaml\na: 1\n```"

        self.assertIs(split_segments(text), split_segments(text))
