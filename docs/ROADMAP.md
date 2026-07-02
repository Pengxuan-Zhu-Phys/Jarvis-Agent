# Roadmap

Execution order is now driven by the milestones (M0–M6) in `docs/DESIGN.md` §10; the phases below remain as the original capability checklist (Phase 1/2/3 are absorbed by M2/M4/M1; Phase 4 is realized as the data flywheel, DESIGN §9 / milestone M6).

## Phase 0: Runnable Skeleton — done

- [x] Python package scaffold.
- [x] CLI and TUI shell.
- [x] Textual workbench-style TUI with a plain terminal fallback (see `docs/TUI_DESIGN.md`).
- [x] Local config file.
- [x] MLX-LM subprocess backend.
- [x] Conservative project indexer.
- [x] Lightweight YAML reviewer.
- [x] Workflow engine interfaces.
- [x] Reviewable MLX-LM LoRA command generation.

The TUI design is now feature-complete for the skeleton: home splash, slash/model
pickers, turn history, context meter, simulated streaming, clipboard, and git /
worktree awareness.

## Phase 0.5: Consolidation (next)

Engineering follow-ups surfaced while finishing the TUI:

- Move the Textual `App` subclass to module scope so it can be imported and
  unit-tested; replace the source-substring tests with behavioral ones.
- Add a persistent, streaming model backend (e.g. `mlx_lm.server` or in-process
  `mlx_lm`) so prompts stop cold-loading the model and the UI can stream real tokens.
- Make reference indexing incremental (currently every `/index` re-parses every
  source file) and set the context meter from the model's real context window.
- Make `~/.jarvis/agent_state.json` an explicit override of the TOML, not a silent one.
- Prune dead helpers in `textual_tui` and add a subprocess timeout to `MLXBackend`.

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
