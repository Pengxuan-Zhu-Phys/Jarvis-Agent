from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelStats:
    prompt_tokens: int | None = None
    prompt_tokens_per_second: float | None = None
    generation_tokens: int | None = None
    generation_tokens_per_second: float | None = None
    peak_memory_gb: float | None = None

    @property
    def context_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.generation_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.generation_tokens or 0)

    def format(self) -> str:
        parts: list[str] = []
        if self.prompt_tokens is not None:
            prompt = f"prompt: {self.prompt_tokens} tokens"
            if self.prompt_tokens_per_second is not None:
                prompt += f" @ {self.prompt_tokens_per_second:.2f} tok/s"
            parts.append(prompt)
        if self.generation_tokens is not None:
            generation = f"generation: {self.generation_tokens} tokens"
            if self.generation_tokens_per_second is not None:
                generation += f" @ {self.generation_tokens_per_second:.2f} tok/s"
            parts.append(generation)
        if self.context_tokens is not None:
            parts.append(f"context: {self.context_tokens} tokens")
        if self.peak_memory_gb is not None:
            parts.append(f"peak memory: {self.peak_memory_gb:.2f} GB")
        return " | ".join(parts)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    command: tuple[str, ...] = ()
    returncode: int = 0
    stderr: str = ""
    stats: ModelStats | None = None

    def display_text(self) -> str:
        if self.stats is None:
            return self.text
        metrics = self.stats.format()
        if not metrics:
            return self.text
        return f"{self.text}\n\n[metrics] {metrics}"


class ModelBackend(Protocol):
    def generate(self, prompt: str) -> GenerationResult:
        """Generate text for a prompt."""
