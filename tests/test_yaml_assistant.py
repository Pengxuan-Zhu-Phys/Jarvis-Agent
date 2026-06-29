import tempfile
import unittest
from pathlib import Path

from jarvis_agent.hep import review_yaml_file


class YAMLAssistantTests(unittest.TestCase):
    def test_yaml_review_reports_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            yaml_path = Path(directory) / "config.yaml"
            yaml_path.write_text("run:\n  sampler: test\n", encoding="utf-8")

            review = review_yaml_file(yaml_path)

            self.assertEqual(review.path, yaml_path.resolve())
            self.assertTrue(review.messages)
