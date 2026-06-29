from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess

from jarvis_agent.config import ModelConfig
from jarvis_agent.model.base import GenerationResult, ModelStats


PROMPT_RE = re.compile(r"^Prompt:\s*(\d+)\s*tokens,\s*([0-9.]+)\s*tokens-per-sec\s*$")
GENERATION_RE = re.compile(r"^Generation:\s*(\d+)\s*tokens,\s*([0-9.]+)\s*tokens-per-sec\s*$")
PEAK_MEMORY_RE = re.compile(r"^Peak memory:\s*([0-9.]+)\s*GB\s*$")


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
        text, stats = parse_mlx_output(completed.stdout)
        return GenerationResult(
            text=text,
            command=command,
            returncode=completed.returncode,
            stderr=completed.stderr.strip(),
            stats=stats,
        )


def parse_mlx_output(output: str) -> tuple[str, ModelStats | None]:
    text_lines: list[str] = []
    prompt_tokens: int | None = None
    prompt_tps: float | None = None
    generation_tokens: int | None = None
    generation_tps: float | None = None
    peak_memory_gb: float | None = None

    for line in output.splitlines():
        stripped = line.strip()
        if stripped == "==========":
            continue
        if matched := PROMPT_RE.match(stripped):
            prompt_tokens = int(matched.group(1))
            prompt_tps = float(matched.group(2))
            continue
        if matched := GENERATION_RE.match(stripped):
            generation_tokens = int(matched.group(1))
            generation_tps = float(matched.group(2))
            continue
        if matched := PEAK_MEMORY_RE.match(stripped):
            peak_memory_gb = float(matched.group(1))
            continue
        text_lines.append(line)

    stats = None
    if any(value is not None for value in (prompt_tokens, generation_tokens, peak_memory_gb)):
        stats = ModelStats(
            prompt_tokens=prompt_tokens,
            prompt_tokens_per_second=prompt_tps,
            generation_tokens=generation_tokens,
            generation_tokens_per_second=generation_tps,
            peak_memory_gb=peak_memory_gb,
        )
    return "\n".join(text_lines).strip(), stats
