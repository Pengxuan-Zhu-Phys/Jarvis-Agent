from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    text: str
    command: tuple[str, ...] = ()
    returncode: int = 0
    stderr: str = ""


class ModelBackend(Protocol):
    def generate(self, prompt: str) -> GenerationResult:
        """Generate text for a prompt."""

