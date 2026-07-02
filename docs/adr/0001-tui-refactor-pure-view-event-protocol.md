# ADR 0001: TUI pure/view split and agent event protocol

## Status

Accepted.

## Context

`jarvis_agent.textual_tui` previously kept the Textual app as a nested class inside
`run_textual_ui()` to defer the optional Textual import. That made the app hard to
import, test, and evolve toward structured agent-loop output.

## Decision

Split `textual_tui` into a package. Keep pure helpers importable from package scope,
load the Textual app lazily, and define `jarvis_agent.protocol` as the UI-agnostic
event contract for future transcript rendering.

## Consequences

Existing imports from `jarvis_agent.textual_tui` continue to work through
back-compatible re-exports. Textual-dependent classes live in
`jarvis_agent.textual_tui.app` and can be tested directly when the optional TUI
dependency is installed.
