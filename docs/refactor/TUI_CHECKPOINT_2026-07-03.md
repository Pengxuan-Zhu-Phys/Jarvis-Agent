# TUI Checkpoint 2026-07-03

## Completed scope

- `textual_tui.py` has been split into the `jarvis_agent.textual_tui` package.
- Output rendering now goes through protocol events and `TranscriptView` blocks.
- The composer, history, streaming, animation, git status, and text utilities are
  separated into focused modules.
- The output pane preserves the user's scroll position when they scroll away from
  the bottom, then resumes auto-follow after they return to the bottom.
- The Grok-style run row is implemented:
  - thinking status is compact: `Thinking... <seconds>s`
  - responding status is compact: `Responding... <seconds>s`
  - the former clock slot shows input/output token direction while active
  - `[stop]` uses normal `#134A8D` text and bold `#F6D33E` hover text
  - the run control right edge aligns with the composer right edge
- Stop is request-scoped at the UI layer:
  - responding stop immediately halts the simulated visible stream
  - thinking stop restores the UI and ignores stale background results
  - cancelled thinking results are not written to session history

## Smoke checklist

- Long assistant output can be scrolled manually without being forced to the
  bottom by continued output.
- Returning to the bottom re-enables automatic follow.
- `[stop]` during responding clears active generation state and returns the clock.
- `[stop]` during thinking clears active generation state; late background output
  is ignored and does not enter session history.
- Run control remains right-aligned to the composer after layout refresh.

## Verification

- `PYTHONPATH=src python3 -m unittest discover -s tests`
- `PYTHONPATH=src python3 scripts/verify_tui_parity.py`

## Remaining M0 migration

Current stop behavior is still a UI detach/cancel guard, not backend cancellation.
The next runtime work should introduce `CancelToken`, `ChatBackend`, true streaming
events, and later wire Textual generation to `asyncio.create_task(...)` instead of
daemon threads around synchronous dispatch.
