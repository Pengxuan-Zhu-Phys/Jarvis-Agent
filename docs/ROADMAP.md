# Roadmap

## Phase 0: Runnable Skeleton

- Python package scaffold.
- CLI and TUI shell.
- Textual workbench-style TUI with a plain terminal fallback.
- Local config file.
- MLX-LM subprocess backend.
- Conservative project indexer.
- Lightweight YAML reviewer.
- Workflow engine interfaces.
- Reviewable MLX-LM LoRA command generation.

## Phase 1: HEP Package Understanding

- Add package profiles for Jarvis-HEP, GAMBIT, Rivet, MadGraph, micrOMEGAs, and common YAML-driven workflows.
- Build richer source maps from docs, examples, CMake files, Python entrypoints, and YAML schemas.
- Add retrieval over indexed snippets with stable path references.
- Add a project memory store that records user-approved package facts.

## Phase 2: YAML Assistant

- Add schema-like validators per package profile.
- Detect unknown keys, suspicious values, missing required blocks, path issues, and incompatible options.
- Provide patch-style YAML suggestions.
- Run package-native validation commands where available.

## Phase 3: Automation Workflows

- Add workflow definitions for indexing, YAML review, benchmark runs, result summarization, and package setup.
- Add resumable execution state.
- Add guarded shell execution with explicit command review.

## Phase 4: Fine-Tuning / Adapter Tuning

- Curate instruction datasets from:
  - package docs,
  - examples,
  - validated YAML repairs,
  - code explanation tasks,
  - user-approved troubleshooting sessions.
- Add dataset builders with provenance metadata.
- Use MLX-LM LoRA/adapter training first, not full fine-tuning.
- Keep evaluation sets separate from training examples.

## Phase 5: Evaluation

- Add regression tasks:
  - explain package entrypoints,
  - repair broken YAML,
  - choose the correct run command,
  - summarize package errors,
  - avoid hallucinating unavailable options.
- Track exact model, adapter, dataset hash, and package revision.
