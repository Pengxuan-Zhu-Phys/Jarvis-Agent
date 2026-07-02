import unittest

from jarvis_agent.textual_tui.streaming import StreamController


class StreamControllerTests(unittest.TestCase):
    def test_batches_until_interval_or_size_threshold(self) -> None:
        controller = StreamController(flush_interval=1.0, max_buffer_chars=5)
        controller.append("ab")

        self.assertFalse(controller.should_flush(now=0.1))

        controller.append("cde")
        self.assertTrue(controller.should_flush(now=0.2))
        self.assertEqual(controller.flush(now=0.2), "abcde")
        self.assertEqual(controller.flush(now=0.3), "")
