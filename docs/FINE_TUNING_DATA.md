# Fine-Tuning Data

The first training path should be LoRA or DoRA adapter tuning through `mlx_lm.lora`.

## Dataset Shape

MLX-LM accepts a directory containing:

- `train.jsonl`
- `valid.jsonl`
- `test.jsonl`

Use chat-style records when possible:

```json
{"messages":[{"role":"user","content":"Explain this GAMBIT YAML block..."},{"role":"assistant","content":"..."}]}
```

## Data Sources

Good sources:

- package docs,
- package examples,
- known-good YAML files,
- broken YAML plus reviewed fixes,
- user-approved troubleshooting transcripts,
- code explanation tasks tied to exact paths and revisions.

Avoid:

- unreviewed model outputs,
- private user paths without consent,
- examples without package version metadata,
- mixing evaluation examples into training data.

## Minimal Command

```bash
jarvis-agent lora-command \
  --data data/hep_lora \
  --adapter-path adapters/qwen3-coder-hep \
  --iters 100
```

Review the printed command, then run it from a normal terminal with Metal access.

