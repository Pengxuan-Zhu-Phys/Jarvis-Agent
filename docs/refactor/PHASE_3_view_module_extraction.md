# Phase 3 View Module Extraction

## Scope

- Extracted composer constants, `PromptTextArea`, and visual-line calculation to
  `textual_tui/composer.py`.
- Extracted `TurnRecord`, `HistoryModel`, and pure history label/expansion helpers
  to `textual_tui/history.py`.
- Expanded `textual_tui/animation.py` with pure logo-monitor rendering functions.
- Updated `JarvisAgentApp` to call the extracted modules while keeping router and
  transcript behavior unchanged.

## Interface changes

- New import path: `jarvis_agent.textual_tui.composer.PromptTextArea`.
- New import path: `jarvis_agent.textual_tui.history.HistoryModel`.
- New import path: `jarvis_agent.textual_tui.animation.render_logo_monitor_frame`.

## Parity verification

- `PYTHONPATH=src python3 -m unittest discover -s tests` passed.
- `PYTHONPATH=src python3 scripts/verify_tui_parity.py` passed.
- Import check for `PromptTextArea`, `HistoryModel`, and
  `render_logo_monitor_frame` passed.

## Jarvis-HEP integration impact

None beyond the Phase 2 protocol/transcript contract. This phase only moves TUI
view support logic into smaller modules.

## Follow-ups

- Phase 4 should delete confirmed-dead methods and replace any remaining fragile
  checks with behavioral/unit coverage.
