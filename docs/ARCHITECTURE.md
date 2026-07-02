# Architecture

System-level design (agent loop, context engineering, information system, local runtime, tools, data flywheel, and the HEP-package → Jarvis-HEP YAML pipeline) lives in `docs/DESIGN.md`; the engineering-level spec (module layout, interface signatures, data schemas, work breakdown) lives in `docs/TECH_DESIGN.md`; this file is the code-level module map of what currently exists.

Jarvis-Agent is split into narrow modules so the model backend, package analysis, YAML help, workflows, and terminal UI can evolve independently.

## Layers

- `jarvis_agent.cli`: command-line entrypoint.
- `jarvis_agent.textual_tui`: Textual workbench-style terminal UI (see `docs/TUI_DESIGN.md`).
- `jarvis_agent.tui`: shared command router (`TerminalUI.dispatch`) and plain terminal fallback.
- `jarvis_agent.config`: project and model configuration.
- `jarvis_agent.model`: model backend contracts and MLX-LM subprocess integration.
- `jarvis_agent.project`: codebase indexing and source selection.
- `jarvis_agent.hep`: HEP-oriented helpers such as YAML review and source explanation prompts.
- `jarvis_agent.agent_actions`: natural-language intent detection and the agent system prompt.
- `jarvis_agent.session`: append-only JSONL session history.
- `jarvis_agent.workflows`: repeatable task orchestration.

## Command Routing

Both UIs share one router. `TerminalUI.dispatch` is the single source of truth for
command behavior and session recording; the Textual UI adds presentation only and
never re-implements command logic. Natural-language input is checked for an index
intent (`agent_actions.detect_agent_action`), otherwise sent to the model with the
agent system prompt, and the reply is scanned for an `[ACTION: INDEX]` marker.

## Model Execution

`WorkflowEngine.ask_model` calls `MLXBackend`, which shells out to `mlx_lm.generate`
as a one-shot subprocess per prompt. This means the model is cold-loaded on every
request and returns its full output at once; the Textual UI simulates streaming on
top of that captured text. A persistent, streaming backend is the main planned
change to this layer (see `docs/ROADMAP.md`).

## Design Rules

- Keep model calls behind `ModelBackend`.
- Keep package indexing deterministic and inspectable.
- Treat generated YAML as a proposal until validated by package-specific checks.
- Store workflow decisions in files, not in chat-only memory.
- Prefer local, private execution by default.
- TUI agent commands use slash prefixes such as `/index`, `/yaml`, and `/ask`; plain text is treated as model chat input.
- Textual is an optional dependency; the CLI falls back to the plain terminal UI when it is unavailable.
- Startup branding is loaded from `Jarvis -v` and the Jarvis-HEP `jarvishep/card/logo` asset when available.
- The Textual home page is available through `/home`.
- `/index` stores an inspectable JSON codebase cache under `.jarvis/index/codebase_index.json`; see `docs/CODEBASE_INDEX_DESIGN.md`.

## Configuration Precedence

Effective config is `.jarvis-agent.toml` (or defaults) with `~/.jarvis/agent_state.json`
layered on top for the model block. The state file is (re)written on every
`load_config`, so once a model has been recorded there, editing the `[model]` block
in the TOML has no effect until the state file is cleared or `/model` is used. This
is a known rough edge; the state file should become an explicit override, not a
silent one.

## Near-Term Target

The first useful agent should be able to:

1. Index a package root.
2. Identify likely entrypoints, examples, config files, and docs.
3. Explain selected files with citations to paths.
4. Review YAML files for syntax, anchors, duplicate-looking sections, and likely package-specific issues.
5. Run a configured MLX model for natural-language help.
