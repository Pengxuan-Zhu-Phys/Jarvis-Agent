# Phase 1 Package Split

## Scope

- Converted `src/jarvis_agent/textual_tui.py` into the `jarvis_agent.textual_tui`
  package.
- Moved `JarvisAgentApp` and `PromptTextArea` to module scope in
  `textual_tui/app.py`.
- Extracted inline Textual CSS to `textual_tui/styles.tcss`.
- Added the initial UI-agnostic `jarvis_agent.protocol.events` contract.

## Interface changes

- `jarvis_agent.textual_tui.run_textual_ui` now lazy-imports the Textual app.
- Back-compatible helper imports remain available from `jarvis_agent.textual_tui`.
- New protocol imports are available from `jarvis_agent.protocol`.

## Parity verification

- `PYTHONPATH=src python3 -m unittest discover -s tests` passed.
- `PYTHONPATH=src python3 -c "import jarvis_agent.textual_tui; from jarvis_agent.protocol.events import UserPrompt"` passed.

## Jarvis-HEP integration impact

The shared `jarvis_agent.protocol` path now exists with v1 frozen event dataclasses,
but the current TUI has not started consuming events yet.

## Follow-ups

- Wire the transcript/output subsystem to consume `AgentEvent`.
- Continue extracting history, composer, streaming, and animation view modules.
