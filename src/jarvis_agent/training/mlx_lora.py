from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis_agent.config import DEFAULT_MODEL


@dataclass(frozen=True)
class LoRAConfig:
    model: str = DEFAULT_MODEL
    data: Path = Path("data/hep_lora")
    adapter_path: Path = Path("adapters/qwen3-coder-hep")
    fine_tune_type: str = "lora"
    batch_size: int = 1
    iters: int = 100
    learning_rate: float = 1e-5
    max_seq_length: int = 4096
    num_layers: int = 16
    grad_checkpoint: bool = True
    steps_per_report: int = 10
    steps_per_eval: int = 50
    save_every: int = 50


def build_lora_command(config: LoRAConfig, executable: str = "mlx_lm.lora") -> tuple[str, ...]:
    command = [
        executable,
        "--model",
        config.model,
        "--train",
        "--data",
        str(config.data),
        "--fine-tune-type",
        config.fine_tune_type,
        "--adapter-path",
        str(config.adapter_path),
        "--batch-size",
        str(config.batch_size),
        "--iters",
        str(config.iters),
        "--learning-rate",
        str(config.learning_rate),
        "--max-seq-length",
        str(config.max_seq_length),
        "--num-layers",
        str(config.num_layers),
        "--steps-per-report",
        str(config.steps_per_report),
        "--steps-per-eval",
        str(config.steps_per_eval),
        "--save-every",
        str(config.save_every),
    ]
    if config.grad_checkpoint:
        command.append("--grad-checkpoint")
    return tuple(command)

