# M0 Runtime Types

## Scope

- Added `jarvis_agent.runtime` as the new async chat runtime contract.
- Added frozen/slots runtime data types:
  - `ChatMessage`
  - `ToolCall`
  - `ToolSpec`
  - `Usage`
  - `TextDelta`
  - `ToolCallsReady`
  - `UsageReport`
  - `StreamEnd`
  - `BackendFailure`
- Added `CancelToken` for cooperative cancellation across UI, agent loop, and
  backends.
- Added `RetryPolicy` for recoverable backend failures.
- Added `ChatBackend` protocol with stable `id()`, `context_window()`, and async
  streaming `chat(...)`.

## Interface status

This is a contract-only step. The existing synchronous `model/` backend and
`TerminalUI.dispatch(...)` paths remain unchanged. Future M0 steps will add an
MLX server backend, a subprocess adapter for the current MLX backend, and then
wire the Textual TUI to real streamed `ChatEvent` values.

## Verification

- `PYTHONPATH=src python3 -m unittest tests.test_runtime_types`
- `PYTHONPATH=src python3 -m unittest discover -s tests`
