# Phase 4 Cleanup and Tests

## Scope

- Removed confirmed-dead app methods: `render_turn_panel`, `update_turn_panel`,
  `render_topbar`, `render_repo_info`, `toggle_history_prompt`,
  `visible_history_turn_index`, `write_wrapped_output`, `output_wrap_width`, and
  `reflow_output`.
- Removed stale manual output wrapping state now superseded by `TranscriptView`.
- Removed the obsolete `_compact_model_name` compatibility alias.
- Added behavioral Textual tests for prompt submission, `/index`, and unknown
  command rendering.

## Interface changes

- `jarvis_agent.textual_tui._compact_model_name` is removed. Use
  `jarvis_agent.config.compact_model_name`.
- `JarvisAgentApp` no longer exposes the removed internal helper methods listed
  above.

## Parity verification

- `PYTHONPATH=src python3 -m unittest discover -s tests` passed.
- `PYTHONPATH=src python3 scripts/verify_tui_parity.py` passed.

## Jarvis-HEP integration impact

None. The shared `jarvis_agent.protocol` contract from Phase 2 is unchanged.

## Follow-ups

- Add richer golden render snapshots for settled assistant markdown/code blocks
  when the project adopts a snapshot convention.
