# Jarvis-Agent

Jarvis-Agent is the local assistant layer for HEP software packages. The intended path is:

1. Use a local Qwen3-Coder model through MLX-LM.
2. Index large HEP codebases such as GAMBIT, Jarvis-HEP, and related packages.
3. Help users understand package structure, workflows, and configuration files.
4. Review and generate YAML settings with package-aware context.
5. Run repeatable local workflows from a terminal UI.
6. Later fine-tune or adapter-tune the model on curated HEP package examples.

This repository currently contains a runnable MVP scaffold. It does not yet claim deep HEP reasoning; it defines the interfaces and first workflows needed to build that system cleanly.

## Quick Start

```bash
python3 -m pip install -e '.[tui,yaml]'
jarvis-agent init
jarvis-agent tui --project /path/to/HEP/package
```

For Qwen3-Coder via MLX-LM:

```bash
hf auth login
mlx_lm.generate \
  --model mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit \
  --prompt "hello"
```

Then configure `.jarvis-agent.toml`:

```toml
[model]
backend = "mlx"
model = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
max_tokens = 2048
temperature = 0.2
```

## TUI Commands

`jarvis-agent tui` uses Textual when the `tui` extra is installed. Without Textual, it falls back to the plain terminal UI.

Inside the TUI:

- `/help` shows commands.
- `/status` shows project and model status.
- `/index` scans the configured project.
- `/explain PATH` builds an explanation prompt for a source file.
- `/yaml PATH` performs a lightweight YAML review.
- `/ask PROMPT` sends a prompt to the configured model backend.
- `/clear` redraws the startup page.
- `/quit` exits.

Plain text without a leading slash is sent to the configured model as a chat prompt.

Plain fallback mode:

```bash
jarvis-agent tui --plain --project /path/to/HEP/package
```

## LoRA Command

Jarvis-Agent can print a reviewed MLX-LM LoRA command:

```bash
jarvis-agent lora-command \
  --data data/hep_lora \
  --adapter-path adapters/qwen3-coder-hep \
  --iters 100
```

Run the printed `mlx_lm.lora ...` command from a normal terminal with Metal access.

## Smoke Checks

Without installing:

```bash
PYTHONPATH=src python3 -m jarvis_agent index --project .
PYTHONPATH=src python3 -m jarvis_agent yaml-review examples/hep-config.yaml --project .
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Current Boundaries

- The MLX backend is a subprocess wrapper around `mlx_lm.generate`.
- YAML parsing uses `PyYAML` if installed, otherwise falls back to structural text checks.
- Project indexing is intentionally conservative and ignores build/cache/vendor-heavy directories.
- Fine-tuning execution and dataset building are not automated yet; `lora-command` only prints a reviewable MLX-LM command.
