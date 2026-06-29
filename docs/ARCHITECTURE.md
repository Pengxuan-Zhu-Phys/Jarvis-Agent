# Architecture

Jarvis-Agent is split into narrow modules so the model backend, package analysis, YAML help, workflows, and terminal UI can evolve independently.

## Layers

- `jarvis_agent.cli`: command-line entrypoint.
- `jarvis_agent.textual_tui`: Textual workbench-style terminal UI.
- `jarvis_agent.tui`: shared command router and plain terminal fallback.
- `jarvis_agent.config`: project and model configuration.
- `jarvis_agent.model`: model backend contracts and MLX-LM subprocess integration.
- `jarvis_agent.project`: codebase indexing and source selection.
- `jarvis_agent.hep`: HEP-oriented helpers such as YAML review and source explanation prompts.
- `jarvis_agent.workflows`: repeatable task orchestration.

## Design Rules

- Keep model calls behind `ModelBackend`.
- Keep package indexing deterministic and inspectable.
- Treat generated YAML as a proposal until validated by package-specific checks.
- Store workflow decisions in files, not in chat-only memory.
- Prefer local, private execution by default.
- TUI agent commands use slash prefixes such as `/index`, `/yaml`, and `/ask`; plain text is treated as model chat input.
- Textual is an optional dependency; the CLI falls back to the plain terminal UI when it is unavailable.

## Near-Term Target

The first useful agent should be able to:

1. Index a package root.
2. Identify likely entrypoints, examples, config files, and docs.
3. Explain selected files with citations to paths.
4. Review YAML files for syntax, anchors, duplicate-looking sections, and likely package-specific issues.
5. Run a configured MLX model for natural-language help.
