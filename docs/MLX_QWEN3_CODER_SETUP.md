# MLX Qwen3-Coder Setup

## Hugging Face Login

Create a read token at:

https://huggingface.co/settings/tokens

Then run:

```bash
hf auth login
hf auth whoami
```

## Download and Smoke Test

```bash
mlx_lm.generate \
  --model mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit \
  --prompt "hello"
```

If download appears stuck after using `Ctrl-Z`, check suspended jobs:

```bash
jobs -l
```

Terminate old suspended downloads before starting a new one:

```bash
kill PID
```

## Jarvis-Agent Configuration

```bash
jarvis-agent init
```

Edit `.jarvis-agent.toml`:

```toml
[model]
backend = "mlx"
model = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
max_tokens = 2048
temperature = 0.2
```

## Fine-Tuning Direction

Start with LoRA/adapter tuning through MLX-LM rather than full fine-tuning. The agent should first build small, auditable datasets from package docs, examples, and user-approved YAML repairs.

