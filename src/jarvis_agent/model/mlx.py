from __future__ import annotations

from dataclasses import dataclass
import subprocess

from jarvis_agent.config import ModelConfig
from jarvis_agent.model.base import GenerationResult


@dataclass(frozen=True)
class MLXBackend:
    config: ModelConfig
    executable: str = "mlx_lm.generate"
    timeout_seconds: int | None = None

    def command_for(self, prompt: str) -> tuple[str, ...]:
        return (
            self.executable,
            "--model",
            self.config.model,
            "--prompt",
            prompt,
            "--max-tokens",
            str(self.config.max_tokens),
            "--temp",
            str(self.config.temperature),
        )

    def generate(self, prompt: str) -> GenerationResult:
        command = self.command_for(prompt)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        return GenerationResult(
            text=completed.stdout.strip(),
            command=command,
            returncode=completed.returncode,
            stderr=completed.stderr.strip(),
        )

