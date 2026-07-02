# Phase 2 Output Subsystem

## Scope

- Added `protocol.EventBus` for async producer/consumer decoupling.
- Added `textual_tui.output` with pure fenced-code parsing, block widgets, and
  `TranscriptView`.
- Replaced the Textual `Log` output pane with a block-based `TranscriptView` while
  preserving `id="log"` for surrounding app code.
- Added `StreamController` to batch simulated response-stream deltas before repaint.
- Added `scripts/verify_tui_parity.py` for transcript rendering smoke checks.

## Interface changes

- New import path: `jarvis_agent.protocol.EventBus`.
- New import path: `jarvis_agent.textual_tui.output.blocks.split_segments`.
- The TUI output widget at `#log` is now `TranscriptView`, not Textual `Log`.

## Parity verification

- `PYTHONPATH=src python3 -m unittest discover -s tests` passed.
- `PYTHONPATH=src python3 scripts/verify_tui_parity.py` passed.

## Jarvis-HEP integration impact

Agent-loop output can now be emitted as `AgentEvent` instances and consumed by the
same transcript view without depending on Textual inside producer code.

## Follow-ups

- Extract history, composer, and remaining streaming/view coordination modules in
  Phase 3.
