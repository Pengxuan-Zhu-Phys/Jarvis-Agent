import unittest
from pathlib import Path

from jarvis_agent.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_with_project_override(self) -> None:
        path = Path(self._testMethodName).resolve()
        config = load_config(path=None, project_override=path)
        self.assertEqual(config.project.root, path)
        self.assertEqual(config.model.backend, "mlx")
