import unittest

from jarvis_agent.model.mlx import parse_mlx_output


class MLXBackendTests(unittest.TestCase):
    def test_parse_mlx_output_extracts_stats(self) -> None:
        text, stats = parse_mlx_output(
            "==========\n"
            "hello from model\n"
            "Prompt: 18 tokens, 1.062 tokens-per-sec\n"
            "Generation: 227 tokens, 83.791 tokens-per-sec\n"
            "Peak memory: 17.238 GB\n"
        )

        self.assertEqual(text, "hello from model")
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.prompt_tokens, 18)
        self.assertEqual(stats.generation_tokens, 227)
        self.assertEqual(stats.context_tokens, 245)
        self.assertEqual(stats.format(), "prompt: 18 tokens @ 1.06 tok/s | generation: 227 tokens @ 83.79 tok/s | context: 245 tokens | peak memory: 17.24 GB")

