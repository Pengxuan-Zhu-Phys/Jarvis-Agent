import unittest
from pathlib import Path

from jarvis_agent.training import LoRAConfig, build_lora_command


class TrainingTests(unittest.TestCase):
    def test_build_lora_command(self) -> None:
        command = build_lora_command(
            LoRAConfig(model="local-model", data=Path("data"), adapter_path=Path("adapters"), iters=5)
        )

        self.assertIn("mlx_lm.lora", command)
        self.assertIn("--train", command)
        self.assertIn("--data", command)
        self.assertIn("data", command)
        self.assertIn("--adapter-path", command)
        self.assertIn("adapters", command)
