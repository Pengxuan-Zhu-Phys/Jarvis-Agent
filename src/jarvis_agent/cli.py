from __future__ import annotations

import argparse
from pathlib import Path

from jarvis_agent.config import (
    CONFIG_NAME,
    discover_mlx_models,
    load_config,
    local_available_models,
    save_local_model_state_with_models,
    write_default_config,
)
from jarvis_agent.tui import TerminalUI
from jarvis_agent.textual_tui import TextualUnavailable, run_textual_ui
from jarvis_agent.training import LoRAConfig, build_lora_command
from jarvis_agent.workflows import WorkflowEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis-agent")
    parser.add_argument("--config", type=Path, help="Path to .jarvis-agent.toml")
    subparsers = parser.add_subparsers(dest="command")

    init = subparsers.add_parser("init", help="Write a default local config")
    init.add_argument("--project", type=Path, default=Path.cwd(), help="Project root for the default config")
    init.add_argument("--output", type=Path, default=Path(CONFIG_NAME), help="Config output path")

    tui = subparsers.add_parser("tui", help="Start the terminal UI")
    tui.add_argument("--project", type=Path, help="Override configured project root")
    tui.add_argument("--plain", action="store_true", help="Use the fallback plain terminal UI")

    index = subparsers.add_parser("index", help="Index the configured project")
    index.add_argument("--project", type=Path, help="Override configured project root")

    explain = subparsers.add_parser("explain", help="Build an explanation prompt for a file")
    explain.add_argument("path", type=Path)
    explain.add_argument("--project", type=Path, help="Override configured project root")

    yaml_review = subparsers.add_parser("yaml-review", help="Review a YAML file")
    yaml_review.add_argument("path", type=Path)
    yaml_review.add_argument("--project", type=Path, help="Override configured project root")

    ask = subparsers.add_parser("ask", help="Ask the configured model")
    ask.add_argument("prompt")
    ask.add_argument("--project", type=Path, help="Override configured project root")

    models = subparsers.add_parser("models", help="List or scan local MLX-LM models")
    models.add_argument("action", nargs="?", choices=["list", "scan"], default="list")
    models.add_argument("--project", type=Path, help="Override configured project root")

    lora = subparsers.add_parser("lora-command", help="Print an MLX-LM LoRA training command")
    lora.add_argument("--model", default=None, help="Model path or Hugging Face repo")
    lora.add_argument("--data", type=Path, default=Path("data/hep_lora"), help="Directory with train/valid/test jsonl")
    lora.add_argument("--adapter-path", type=Path, default=Path("adapters/qwen3-coder-hep"))
    lora.add_argument("--fine-tune-type", choices=["lora", "dora", "full"], default="lora")
    lora.add_argument("--batch-size", type=int, default=1)
    lora.add_argument("--iters", type=int, default=100)
    lora.add_argument("--learning-rate", type=float, default=1e-5)
    lora.add_argument("--max-seq-length", type=int, default=4096)
    lora.add_argument("--num-layers", type=int, default=16)
    lora.add_argument("--no-grad-checkpoint", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        write_default_config(args.output, args.project)
        print(f"Wrote {args.output}")
        return 0

    if args.command is None:
        parser.print_help()
        return 0

    config = load_config(args.config, getattr(args, "project", None))
    engine = WorkflowEngine(config)

    if args.command == "tui":
        if args.plain:
            return TerminalUI(config).run()
        try:
            return run_textual_ui(config)
        except TextualUnavailable as exc:
            print(f"{exc}")
            print("Falling back to the plain terminal UI.")
        return TerminalUI(config).run()
    if args.command == "index":
        print(engine.index_summary())
        return 0
    if args.command == "explain":
        print(engine.explain_file_prompt(_resolve_input_path(args.path, config.project.root)))
        return 0
    if args.command == "yaml-review":
        print(engine.review_yaml(_resolve_input_path(args.path, config.project.root)))
        return 0
    if args.command == "ask":
        print(engine.ask_model(args.prompt))
        return 0
    if args.command == "models":
        if args.action == "scan":
            models = discover_mlx_models()
            state_path = save_local_model_state_with_models(config, models)
            if models:
                print(f"Discovered {len(models)} downloaded MLX-LM model(s):")
                for index, model in enumerate(models, start=1):
                    print(f"  {index}. {model}")
            else:
                print("No downloaded MLX-LM models were found in the Hugging Face cache.")
            print(f"Saved global model state to {state_path}")
            return 0
        for index, model in enumerate(local_available_models((config.model.model,)), start=1):
            marker = "*" if model == config.model.model else " "
            print(f"{marker} {index}. {model}")
        return 0
    if args.command == "lora-command":
        lora_config = LoRAConfig(
            model=args.model or config.model.model,
            data=args.data,
            adapter_path=args.adapter_path,
            fine_tune_type=args.fine_tune_type,
            batch_size=args.batch_size,
            iters=args.iters,
            learning_rate=args.learning_rate,
            max_seq_length=args.max_seq_length,
            num_layers=args.num_layers,
            grad_checkpoint=not args.no_grad_checkpoint,
        )
        print(" ".join(build_lora_command(lora_config)))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _resolve_input_path(path: Path, project_root: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()
