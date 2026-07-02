from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


Role = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "tool_calls", "length", "cancelled", "error"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCallsReady:
    calls: tuple[ToolCall, ...]


@dataclass(frozen=True, slots=True)
class UsageReport:
    usage: Usage


@dataclass(frozen=True, slots=True)
class StreamEnd:
    finish_reason: FinishReason


@dataclass(frozen=True, slots=True)
class BackendFailure:
    kind: str
    message: str
    recoverable: bool


ChatEvent = TextDelta | ToolCallsReady | UsageReport | StreamEnd | BackendFailure
