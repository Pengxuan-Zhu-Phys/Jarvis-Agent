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
- `/home` opens the Jarvis-Agent home page.
- `/status` shows project and model status.
- `/model` lists available MLX models.
- `/model N` or `/model HF_REPO` switches the active MLX model.
- `/resume` lists saved sessions from `$HOME/.jarvis/sessions.jsonl`.
- `/resume latest` or `/resume SESSION_ID` prints a saved transcript.
- `/index` scans the configured project and writes `.jarvis/index/codebase_index.json`.
- `/explain PATH` builds an explanation prompt for a source file.
- `/yaml PATH` performs a lightweight YAML review.
- `/ask PROMPT` sends a prompt to the configured model backend.
- `/clear` clears the session output.
- `/quit` exits.

Plain text without a leading slash is sent to the configured model as a chat prompt.

Natural language index requests are handled as an agent action. Phrases like `帮我把当前项目索引一下`, `更新一下代码索引`, `scan project`, or `rebuild symbols` run the same incremental indexer as `/index` and return a structured summary.

The Textual UI includes an interactive command picker. Type `/` to show available commands, press `Tab` to complete the highlighted command, use `Up`/`Down` to move through suggestions, and press `Enter` or click a row to run it. Completing `/model` opens the model picker; choose with `Up`/`Down` + `Enter`, click a model, or press `1`/`2`.

The home panel uses Jarvis-HEP branding from `Jarvis -v` when available. In the Textual UI, the home page appears at startup; normal commands collapse it, and `/home` opens it again. The home page renders one 8x8 round-dot Jarvis monitor: the left 4x8 half uses blue background with white active cells, the right 4x8 half uses dark-blue background with yellow active cells, the banner text keeps the `Jarvis -v` alignment and gradient colors, and the animated resource distributions settle into the Jarvis logo.

Jarvis-Agent writes lightweight session history to `$HOME/.jarvis/sessions.jsonl`. `/resume` lists previous sessions and `/resume latest` shows the latest transcript. Model context replay is not injected into prompts yet; the first implementation restores the visible transcript.

When the local model is running, the Textual UI shows a spinner line with elapsed thinking time, an approximate context token count, and the configured max generation tokens. After the model returns, the answer is streamed into the output pane character by character with a separate `Responding...` status line and visible output speed. MLX-LM token and memory stats are parsed from the model output and appended as `[metrics]` when available.

Selecting text in the Textual UI automatically copies it to the terminal clipboard when the terminal supports OSC52 clipboard writes. The status line briefly shows `Copied selection`.

The Textual layout keeps the latest user turn in a separate top panel with a timestamp, renders model output in a dedicated selectable output pane, and keeps model/runtime details in a bottom status line.

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
- Project indexing writes a JSON + in-memory cache under `.jarvis/index/codebase_index.json`, uses file hashes for incremental updates, and extracts Python/C++ symbols and identifier references with Tree-sitter.
- Fine-tuning execution and dataset building are not automated yet; `lora-command` only prints a reviewable MLX-LM command.
