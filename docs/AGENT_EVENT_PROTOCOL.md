# Agent Event Protocol

`jarvis_agent.protocol` defines the UI-agnostic event contract for agent-loop
output. Producers emit frozen event dataclasses; consumers validate events and
ignore event types they do not understand.

## Version

Current version: `PROTOCOL_VERSION = 1`.

Compatible extensions should use each event's `metadata` mapping. Breaking changes
require bumping the protocol version and keeping a deprecation window for existing
consumers.

## Events

- `UserPrompt(text, timestamp)`: user turn entering the transcript.
- `AssistantTextDelta(text)`: streamed assistant text chunk.
- `AssistantTextEnd()`: assistant stream settled and can be formatted.
- `ToolCallStarted(name, args)`: tool invocation started.
- `ToolResult(name, output, ok=True)`: tool invocation completed.
- `LogLine(text)`: append a line to an active live log block.
- `Status(message)`: transient status.
- `Error(message)`: error transcript entry.
- `Metrics(summary, detail="")`: model or runtime metrics.
- `Summary(title, body)`: structured summary output.

## Validation

Consumers call `validate_event(event)` at their boundary. Validation rejects
unsupported event instances, non-mapping metadata, and future protocol versions
that this consumer cannot safely interpret.

## Event bus

`EventBus` wraps an `asyncio.Queue` and weak subscriber references. Producers call
`publish(event)`; consumers subscribe with a callable that accepts one `AgentEvent`.
The bus validates every published event before dispatch.
